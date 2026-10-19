from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional, Dict, Any
from domain.models import (
    TimeSlot, SlotState, EventKit, Reservation, MaintenanceBlock, 
    ReservationStatus, ClubStanding, ItemAvailability
)
from repository.memory_repo import MemoryRepository
from services.reservation_pipeline import ReservationValidationPipeline

class AvailabilityService:
    """
    Core service for Slot Management and Availability Checking.
    Integrates calendar reservations, 15-minute inspection buffers,
    kit operational state, maintenance blocks, and team eligibility.
    """
    def __init__(self, repo: MemoryRepository, pipeline: Optional[ReservationValidationPipeline] = None):
        self.repo = repo
        self.pipeline = pipeline or ReservationValidationPipeline()
        self.operating_start_hour = 9   # 09:00 AM
        self.operating_end_hour = 17   # 05:00 PM
        self.buffer_minutes = 15       # 15-minute inspection gap

    def get_available_slots(
        self, 
        target_date: date, 
        duration_minutes: int = 60,
        club_id: Optional[str] = None,
        kit_id: Optional[str] = None
    ) -> List[TimeSlot]:
        """
        Calculates all candidate time slots for a given date and evaluates their availability state.
        Enforces 5 checks:
        1. Within operating hours.
        2. Team eligibility (if club_id provided).
        3. Kit completeness and equipment usability.
        4. Maintenance/recovery blocks.
        5. Conflicting reservations & 15-minute inspection gaps.
        """
        if not kit_id:
            kits = self.repo.list_kits()
            if not kits:
                return []
            kit_id = kits[0].kit_id

        kit = self.repo.get_kit(kit_id)

        # Generate candidate slots throughout operating hours
        start_datetime = datetime.combine(target_date, time(self.operating_start_hour, 0)).replace(tzinfo=timezone.utc)
        end_datetime = datetime.combine(target_date, time(self.operating_end_hour, 0)).replace(tzinfo=timezone.utc)

        slots: List[TimeSlot] = []
        current_time = start_datetime
        slot_delta = timedelta(minutes=duration_minutes)
        buffer_delta = timedelta(minutes=self.buffer_minutes)

        while current_time + slot_delta <= end_datetime:
            slot_start = current_time
            slot_end = current_time + slot_delta

            state, reason, res_id, block_id = self._evaluate_slot_state(
                kit_id=kit_id,
                slot_start=slot_start,
                slot_end=slot_end,
                club_id=club_id
            )

            slots.append(TimeSlot(
                start_time=slot_start,
                end_time=slot_end,
                state=state,
                reason=reason,
                reservation_id=res_id,
                block_id=block_id
            ))

            # Step forward by duration + inspection buffer
            current_time = slot_end + buffer_delta

        return slots

    def _evaluate_slot_state(
        self,
        kit_id: str,
        slot_start: datetime,
        slot_end: datetime,
        club_id: Optional[str] = None
    ) -> tuple[SlotState, str, Optional[str], Optional[str]]:
        """Evaluates a single candidate slot against operational and booking rules."""
        kit = self.repo.get_kit(kit_id)
        if not kit:
            return SlotState.EQUIPMENT_BLOCKED, "Kit not found", None, None

        from domain.models import ensure_utc
        slot_start = ensure_utc(slot_start)
        slot_end = ensure_utc(slot_end)

        # 1. Check Kit Operational Usability
        if not kit.is_complete_and_usable:
            return SlotState.EQUIPMENT_BLOCKED, "Kit is incomplete or under repair", None, None

        for eq_type, item_id in kit.assigned_items.items():
            item = self.repo.get_equipment(item_id)
            if not item or item.availability != ItemAvailability.USABLE or item.condition.value != "GOOD":
                return SlotState.EQUIPMENT_BLOCKED, f"Equipment component {eq_type.value} unusable", None, None

        # 2. Check Maintenance Blocks
        blocks = self.repo.list_maintenance_blocks(kit_id)
        for b in blocks:
            b_start = ensure_utc(b.start_time)
            b_end = ensure_utc(b.end_time)
            if b.is_active and not (slot_end <= b_start or slot_start >= b_end):
                return SlotState.MAINTENANCE_BLOCKED, f"Maintenance block: {b.reason}", None, b.block_id

        # 3. Check Reservations and Inspection Gap Buffers
        buffer_delta = timedelta(minutes=self.buffer_minutes)
        existing_reservations = [
            r for r in self.repo.list_reservations()
            if r.kit_id == kit_id and r.status in (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_OUT)
        ]

        for res in existing_reservations:
            r_start = ensure_utc(res.start_time)
            r_end = ensure_utc(res.end_time)

            # Exact overlap with reservation
            if not (slot_end <= r_start or slot_start >= r_end):
                return SlotState.RESERVED, f"Reserved by Club ({r_start.strftime('%H:%M')} - {r_end.strftime('%H:%M')})", res.reservation_id, None

            # Overlap with 15-min inspection buffer
            res_buffered_start = r_start - buffer_delta
            res_buffered_end = r_end + buffer_delta
            if not (slot_end <= res_buffered_start or slot_start >= res_buffered_end):
                return SlotState.INSPECTION_BUFFER, f"15-min mandatory inspection buffer around reservation ({r_start.strftime('%H:%M')}-{r_end.strftime('%H:%M')})", res.reservation_id, None

        # 4. Check Team Eligibility (if club_id passed)
        if club_id:
            club = self.repo.get_club(club_id)
            if club and club.financial_standing == ClubStanding.DEBARRED:
                return SlotState.AVAILABLE, f"Slot physically available, but team '{club.name}' is DEBARRED", None, None

        return SlotState.AVAILABLE, "Slot available for booking", None, None

    def get_kit_calendar(self, kit_id: str, start_dt: datetime, end_dt: datetime) -> List[Dict[str, Any]]:
        """Returns consolidated timeline of reservations, buffers, and maintenance blocks."""
        timeline = []
        buffer_delta = timedelta(minutes=self.buffer_minutes)

        # 1. Reservations & buffers
        reservations = [
            r for r in self.repo.list_reservations()
            if r.kit_id == kit_id and r.start_time < end_dt and r.end_time > start_dt
        ]
        for res in reservations:
            club = self.repo.get_club(res.club_id)
            club_name = club.name if club else "Unknown Club"
            timeline.append({
                "type": "RESERVATION",
                "id": res.reservation_id,
                "title": f"Booking: {club_name}",
                "start_time": res.start_time.isoformat(),
                "end_time": res.end_time.isoformat(),
                "status": res.status.value,
                "club_id": res.club_id
            })
            # Inspection buffer before
            timeline.append({
                "type": "INSPECTION_BUFFER",
                "id": f"buf-pre-{res.reservation_id}",
                "title": "Pre-Inspection Buffer (15m)",
                "start_time": (res.start_time - buffer_delta).isoformat(),
                "end_time": res.start_time.isoformat(),
                "status": "BUFFER"
            })
            # Inspection buffer after
            timeline.append({
                "type": "INSPECTION_BUFFER",
                "id": f"buf-post-{res.reservation_id}",
                "title": "Post-Inspection Buffer (15m)",
                "start_time": res.end_time.isoformat(),
                "end_time": (res.end_time + buffer_delta).isoformat(),
                "status": "BUFFER"
            })

        # 2. Maintenance blocks
        blocks = [
            b for b in self.repo.list_maintenance_blocks(kit_id)
            if b.is_active and b.start_time < end_dt and b.end_time > start_dt
        ]
        for b in blocks:
            timeline.append({
                "type": "MAINTENANCE_BLOCK",
                "id": b.block_id,
                "title": f"Maintenance: {b.reason}",
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "status": "ACTIVE_BLOCK",
                "created_by": b.created_by
            })

        # Sort timeline by start_time
        timeline.sort(key=lambda x: x["start_time"])
        return timeline

    def create_maintenance_block(
        self, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime, 
        reason: str, 
        created_by: str = "College Administrator"
    ) -> MaintenanceBlock:
        """Creates an admin maintenance block on the kit calendar."""
        block = MaintenanceBlock(
            kit_id=kit_id,
            start_time=start_time,
            end_time=end_time,
            reason=reason,
            created_by=created_by,
            is_active=True
        )
        return self.repo.save_maintenance_block(block)

    def get_30_day_availability(
        self,
        start_date: Optional[date] = None,
        kit_id: Optional[str] = None,
        club_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculates a high-level 30-day rolling calendar availability matrix.
        Provides daily status (AVAILABLE, PARTIALLY_BOOKED, FULLY_BOOKED, MAINTENANCE_BLOCKED, EQUIPMENT_BLOCKED)
        and summary metrics for student teams and college administrators.
        """
        if not start_date:
            start_date = date.today()

        if not kit_id:
            kits = self.repo.list_kits()
            if not kits:
                return []
            kit_id = kits[0].kit_id

        kit = self.repo.get_kit(kit_id)
        is_kit_usable = kit.is_complete_and_usable if kit else False

        # Gather active reservations & maintenance blocks
        all_reservations = [
            r for r in self.repo.list_reservations()
            if r.kit_id == kit_id and r.status in (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_OUT, ReservationStatus.RETURNED_PENDING_INSPECTION)
        ]
        all_blocks = [
            b for b in self.repo.list_maintenance_blocks(kit_id)
            if b.is_active
        ]

        calendar_days = []
        for offset in range(30):
            current_day = start_date + timedelta(days=offset)
            day_start = datetime.combine(current_day, time(self.operating_start_hour, 0)).replace(tzinfo=timezone.utc)
            day_end = datetime.combine(current_day, time(self.operating_end_hour, 0)).replace(tzinfo=timezone.utc)

            # Check maintenance blocks on this day
            day_blocks = [
                b for b in all_blocks
                if not (day_end <= b.start_time or day_start >= b.end_time)
            ]

            # Check reservations intersecting this day
            day_reservations = [
                r for r in all_reservations
                if not (day_end <= r.start_time or day_start >= r.end_time)
            ]

            # Calculate total booked minutes
            total_booked_minutes = 0
            for r in day_reservations:
                overlap_start = max(day_start, r.start_time)
                overlap_end = min(day_end, r.end_time)
                if overlap_end > overlap_start:
                    total_booked_minutes += (overlap_end - overlap_start).total_seconds() / 60

            operating_minutes = (self.operating_end_hour - self.operating_start_hour) * 60

            # Determine day status
            if not is_kit_usable:
                day_status = "EQUIPMENT_BLOCKED"
                status_label = "Kit Incomplete"
            elif any(b.start_time <= day_start and b.end_time >= day_end for b in day_blocks):
                day_status = "MAINTENANCE_BLOCKED"
                status_label = "Maintenance Full Day"
            elif total_booked_minutes >= (operating_minutes - 30):
                day_status = "FULLY_BOOKED"
                status_label = "Fully Booked"
            elif len(day_reservations) > 0 or len(day_blocks) > 0:
                day_status = "PARTIALLY_BOOKED"
                status_label = f"{len(day_reservations)} Booking(s)"
            else:
                day_status = "AVAILABLE"
                status_label = "Fully Available"

            calendar_days.append({
                "date": current_day.isoformat(),
                "day_name": current_day.strftime("%a"),
                "day_number": current_day.day,
                "month_name": current_day.strftime("%b"),
                "status": day_status,
                "status_label": status_label,
                "is_available": day_status in ("AVAILABLE", "PARTIALLY_BOOKED"),
                "reservations_count": len(day_reservations),
                "booked_hours": round(total_booked_minutes / 60, 1),
                "available_hours": max(0.0, round((operating_minutes - total_booked_minutes) / 60, 1)),
                "reservations": [
                    {
                        "reservation_id": r.reservation_id,
                        "club_name": self.repo.get_club(r.club_id).name if self.repo.get_club(r.club_id) else "Club",
                        "start_time": r.start_time.isoformat(),
                        "end_time": r.end_time.isoformat(),
                        "status": r.status.value
                    }
                    for r in day_reservations
                ]
            })

        return calendar_days
