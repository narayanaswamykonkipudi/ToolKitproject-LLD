from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone, time
from typing import List, Optional
from domain.models import (
    Club, EventKit, Reservation, ClubStanding, ReservationStatus, 
    ItemAvailability, ItemCondition, EquipmentType, ensure_utc
)
from repository.memory_repo import MemoryRepository

class PipelineResult:
    def __init__(self, is_allowed: bool, rejection_reason: Optional[str] = None, restriction_code: Optional[str] = None):
        self.is_allowed = is_allowed
        self.rejection_reason = rejection_reason
        self.restriction_code = restriction_code

class ReservationFilter(ABC):
    @abstractmethod
    def evaluate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        pass

class ClubDebarmentFilter(ReservationFilter):
    """
    Enforces team booking restriction & account standing:
    If a team has unpaid overdue damage claims or active restriction,
    they are blocked from creating new bookings.
    """
    def evaluate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        if not club_id:
            return PipelineResult(True)  # General slot availability check without team context

        club = repo.get_club(club_id)
        if not club:
            return PipelineResult(False, f"Club {club_id} not registered in system", "CLUB_NOT_FOUND")

        # Check explicit active booking restriction records
        active_restrictions = [
            r for r in repo.list_booking_restrictions(club_id)
            if r.is_active
        ]
        if active_restrictions:
            r = active_restrictions[0]
            return PipelineResult(
                is_allowed=False,
                rejection_reason=f"Booking Restricted: Student '{club.name}' is blocked from booking. Reason: {r.reason}",
                restriction_code="TEAM_BOOKING_RESTRICTED"
            )

        # Check financial standing debarment and unsettled damage penalties
        if club.financial_standing in (ClubStanding.DEBARRED, ClubStanding.PENDING_PAYMENT) or club.outstanding_balance > 0:
            return PipelineResult(
                is_allowed=False,
                rejection_reason=(
                    f"Booking Restricted: Student '{club.name}' has outstanding unpaid damage penalties "
                    f"totaling ₹{club.outstanding_balance:,.2f}. Settle invoice via portal to unblock access."
                ),
                restriction_code="DEBARRED_UNPAID_DAMAGE_PENALTY"
            )

        # Check overdue invoices
        now = datetime.now(timezone.utc)
        invoices = repo.get_invoices_by_club(club_id)
        has_overdue = False
        for inv in invoices:
            if inv.status.value == "OVERDUE" or (inv.status.value == "ISSUED" and ensure_utc(inv.due_date) < now):
                inv.status = inv.status.__class__.OVERDUE
                repo.save_invoice(inv)
                has_overdue = True

        if has_overdue:
            club.financial_standing = ClubStanding.DEBARRED
            repo.save_club(club)
            return PipelineResult(
                is_allowed=False,
                rejection_reason=(
                    f"Booking Restricted: Past-due damage penalty invoice detected for '{club.name}'. "
                    f"Outstanding balance: ₹{club.outstanding_balance:,.2f}."
                ),
                restriction_code="DEBARRED_OVERDUE_INVOICE"
            )

        return PipelineResult(True)

class KitOperationalFilter(ReservationFilter):
    """Verifies that the kit exists, is complete, operational, and all assigned items are usable."""
    def evaluate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        kit = repo.get_kit(kit_id)
        if not kit:
            return PipelineResult(False, f"Kit {kit_id} not found in inventory", "KIT_NOT_FOUND")

        if not kit.is_complete_and_usable:
            return PipelineResult(
                is_allowed=False,
                rejection_reason="Kit availability block: Physical kit is incomplete or undergoing repair. Handover frozen.",
                restriction_code="KIT_INCOMPLETE_MAINTENANCE"
            )

        # Verify all mandatory equipment items are present
        required_types = [EquipmentType.CAMERA, EquipmentType.MICROPHONE, EquipmentType.TRIPOD]
        for req_type in required_types:
            item_id = kit.assigned_items.get(req_type)
            if not item_id:
                return PipelineResult(
                    is_allowed=False,
                    rejection_reason=f"Kit availability block: Mandatory component {req_type.value} is missing from kit bundle.",
                    restriction_code="EQUIPMENT_MISSING_FROM_BUNDLE"
                )

        # Check usability of assigned equipment items
        for eq_type, item_id in kit.assigned_items.items():
            item = repo.get_equipment(item_id)
            if not item or item.availability != ItemAvailability.USABLE or item.condition != ItemCondition.GOOD:
                return PipelineResult(
                    is_allowed=False,
                    rejection_reason=f"Kit availability block: Equipment component {eq_type.value} is missing or defective.",
                    restriction_code="EQUIPMENT_DEFECTIVE"
                )

        return PipelineResult(True)

class MaintenanceBlockFilter(ReservationFilter):
    """Ensures no active organizer maintenance block covers the requested time window."""
    def evaluate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        st = ensure_utc(start_time)
        et = ensure_utc(end_time)
        blocks = repo.list_maintenance_blocks(kit_id)
        active_blocks = [b for b in blocks if b.is_active]

        for block in active_blocks:
            b_start = ensure_utc(block.start_time)
            b_end = ensure_utc(block.end_time)
            # Overlap check
            if not (et <= b_start or st >= b_end):
                return PipelineResult(
                    is_allowed=False,
                    rejection_reason=f"Maintenance block in effect ({b_start.strftime('%H:%M')} - {b_end.strftime('%H:%M')}): {block.reason}",
                    restriction_code="MAINTENANCE_BLOCKED"
                )

        return PipelineResult(True)

class TemporalGapFilter(ReservationFilter):
    """Enforces timing, dates, operating hours, and mandatory 15-minute gap between bookings."""
    def __init__(self, buffer_minutes: int = 15):
        self.buffer = timedelta(minutes=buffer_minutes)

    def evaluate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        st = ensure_utc(start_time)
        et = ensure_utc(end_time)

        # 1. Start vs End time order
        if et <= st:
            return PipelineResult(False, "End time must be strictly after start time", "INVALID_TIME_RANGE")

        # 2. Minimum duration validation (at least 15 minutes)
        if (et - st) < timedelta(minutes=15):
            return PipelineResult(False, "Reservation duration must be at least 15 minutes", "DURATION_TOO_SHORT")

        # 3. Maximum duration validation (multi-day allowed up to 14 days)
        if (et - st) > timedelta(days=14):
            return PipelineResult(False, "Reservation duration cannot exceed 14 consecutive days", "DURATION_TOO_LONG")

        # 4. 30-day advance booking window validation
        now = datetime.now(timezone.utc)
        if (st - now) > timedelta(days=30):
            return PipelineResult(False, "Bookings can only be scheduled within a 30-day advance window", "EXCEEDS_30_DAY_HORIZON")

        # 5. Past time slot validation (allow 5-minute clock drift buffer)
        if et < (now - timedelta(minutes=5)):
            return PipelineResult(False, "Cannot book a time slot in the past", "PAST_TIME_SLOT")

        # 6. Operating hours validation (09:00 - 17:00)
        # Checkout time on start date and return time on end date must both fall within operating hours
        if st.hour < 9 or (st.hour > 17 or (st.hour == 17 and st.minute > 0)):
            return PipelineResult(
                False, 
                f"Booking handover start time ({st.strftime('%H:%M')}) falls outside campus operating hours (09:00 - 17:00)", 
                "OUTSIDE_OPERATING_HOURS"
            )

        if et.hour < 9 or (et.hour > 17 or (et.hour == 17 and et.minute > 0)):
            return PipelineResult(
                False, 
                f"Booking return time ({et.strftime('%H:%M')}) falls outside campus operating hours (09:00 - 17:00)", 
                "OUTSIDE_OPERATING_HOURS"
            )

        # 7. Check conflict with existing reservations & 15-minute gap buffer
        existing_reservations = [
            r for r in repo.list_reservations()
            if r.kit_id == kit_id 
            and r.status in (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_OUT, ReservationStatus.RETURNED_PENDING_INSPECTION)
            and (reservation_id is None or r.reservation_id != reservation_id)
        ]

        for res in existing_reservations:
            r_start = ensure_utc(res.start_time)
            r_end = ensure_utc(res.end_time)
            buffered_start = r_start - self.buffer
            buffered_end = r_end + self.buffer

            # Overlap check with existing reservation plus inspection gap
            if not (et <= buffered_start or st >= buffered_end):
                date_fmt = "%Y-%m-%d %H:%M" if (r_start.date() != r_end.date()) else "%H:%M"
                return PipelineResult(
                    is_allowed=False,
                    rejection_reason=(
                        f"Booking conflict with existing reservation ({r_start.strftime(date_fmt)} - "
                        f"{r_end.strftime(date_fmt)}). 15-minute inspection gap required on both sides."
                    ),
                    restriction_code="INSPECTION_GAP_CONFLICT"
                )

        return PipelineResult(True)

class ReservationValidationPipeline:
    """Chain of Responsibility orchestrator."""
    def __init__(self):
        self.filters: List[ReservationFilter] = [
            ClubDebarmentFilter(),
            KitOperationalFilter(),
            MaintenanceBlockFilter(),
            TemporalGapFilter()
        ]

    def validate(
        self, 
        repo: MemoryRepository, 
        club_id: str, 
        kit_id: str, 
        start_time: datetime, 
        end_time: datetime,
        reservation_id: Optional[str] = None
    ) -> PipelineResult:
        for f in self.filters:
            result = f.evaluate(repo, club_id, kit_id, start_time, end_time, reservation_id)
            if not result.is_allowed:
                return result
        return PipelineResult(True)
