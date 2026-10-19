from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, List
from domain.models import (
    Reservation, ReservationStatus, Incident, ItemCondition,
    EquipmentType, ClubStanding
)
from repository.memory_repo import MemoryRepository
from services.reservation_pipeline import ReservationValidationPipeline, PipelineResult
from services.kit_replacement import KitReplacementService
from services.billing_service import PenaltyBillingService

class ReservationService:
    """Core domain service for managing the complete relay lifecycle."""
    
    def __init__(
        self,
        repo: MemoryRepository,
        replacement_service: KitReplacementService,
        billing_service: PenaltyBillingService
    ):
        self.repo = repo
        self.replacement_service = replacement_service
        self.billing_service = billing_service
        self.pipeline = ReservationValidationPipeline()

    def create_reservation(
        self,
        club_id: str,
        kit_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Tuple[bool, Optional[Reservation], str]:
        """
        Creates a reservation after validating through the pipeline:
        Checks club standing, financial debarment, kit availability, maintenance blocks, and 15-min gap.
        """
        from domain.models import ensure_utc
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)

        validation = self.pipeline.validate(self.repo, club_id, kit_id, start_time, end_time)
        if not validation.is_allowed:
            return False, None, validation.rejection_reason or "Reservation rejected by policy"

        reservation = Reservation(
            club_id=club_id,
            kit_id=kit_id,
            start_time=start_time,
            end_time=end_time,
            status=ReservationStatus.CONFIRMED
        )
        self.repo.save_reservation(reservation)
        return True, reservation, f"Reservation confirmed for slot {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"

    def reschedule_reservation(
        self,
        reservation_id: str,
        new_start_time: datetime,
        new_end_time: datetime
    ) -> Tuple[bool, Optional[Reservation], str]:
        """
        Atomic reschedule operation:
        Validates new slot. If valid, updates reservation. If invalid, retains original booking.
        """
        from domain.models import ensure_utc
        new_start_time = ensure_utc(new_start_time)
        new_end_time = ensure_utc(new_end_time)

        res = self.repo.get_reservation(reservation_id)
        if not res:
            return False, None, "Reservation not found"

        if res.status != ReservationStatus.CONFIRMED:
            return False, None, f"Cannot reschedule reservation in state: {res.status.value}"

        validation = self.pipeline.validate(
            self.repo, res.club_id, res.kit_id, new_start_time, new_end_time, reservation_id=res.reservation_id
        )
        if not validation.is_allowed:
            return False, res, f"Reschedule failed: {validation.rejection_reason}. Original confirmed booking retained."

        # Apply new schedule
        res.start_time = new_start_time
        res.end_time = new_end_time
        self.repo.save_reservation(res)
        return True, res, f"Reservation successfully rescheduled to {new_start_time.strftime('%H:%M')} - {new_end_time.strftime('%H:%M')}"

    def cancel_reservation(self, reservation_id: str, reason: str = "User requested cancellation") -> Tuple[bool, str]:
        """Cancels a confirmed reservation and releases the slot window."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            return False, "Reservation not found"

        if res.status not in (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_OUT):
            return False, f"Cannot cancel reservation in state: {res.status.value}"

        res.status = ReservationStatus.CANCELLED
        res.cancellation_reason = reason
        self.repo.save_reservation(res)
        return True, f"Reservation {reservation_id} has been cancelled. Time slot released."

    def checkout_kit(self, reservation_id: str) -> Tuple[bool, str]:
        """Performs checkout inspection and hands kit over to club after final re-verification."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            return False, "Reservation not found"

        if res.status != ReservationStatus.CONFIRMED:
            return False, f"Cannot checkout reservation in state: {res.status.value}"

        # Immediate pre-handover validation: check team eligibility and kit usability again
        validation = self.pipeline.validate(
            self.repo, res.club_id, res.kit_id, res.start_time, res.end_time, reservation_id=res.reservation_id
        )
        if not validation.is_allowed:
            return False, f"Pre-handover check failed: {validation.rejection_reason}"

        kit = self.repo.get_kit(res.kit_id)
        if not kit or not kit.is_complete_and_usable:
            return False, "Kit is incomplete or unusable. Handover blocked."

        res.status = ReservationStatus.CHECKED_OUT
        self.repo.save_reservation(res)
        return True, "Checkout complete. Equipment handed over to club."

    def submit_return_by_student(self, reservation_id: str, notes: Optional[str] = None) -> Tuple[bool, str]:
        """Student group submits the physical kit back to desk, queueing it for official Admin inspection."""
        res = self.repo.get_reservation(reservation_id)
        if not res:
            return False, "Reservation not found"

        if res.status != ReservationStatus.CHECKED_OUT:
            return False, f"Cannot submit return for reservation in state: {res.status.value}"

        now = datetime.now(timezone.utc)
        res.status = ReservationStatus.RETURNED_PENDING_INSPECTION
        res.returned_at = now
        self.repo.save_reservation(res)
        return True, "Kit submitted at campus desk. Ready for official Admin physical inspection."

    def process_return(
        self,
        reservation_id: str,
        inspections: Dict[EquipmentType, ItemCondition],  # e.g. {MICROPHONE: ItemCondition.DAMAGED}
        defect_notes: Optional[str] = None,
        impose_penalty: bool = True,
        waiver_reason: Optional[str] = None,
        inspector_name: str = "College Administrator"
    ) -> dict:
        """
        Official Inspection workflow (conducted by Admin):
        1. Logs inspection state.
        2. If damage/loss occurs:
           - Immediately replaces the item from college buffer inventory (ensuring kit stays 100% usable).
           - If impose_penalty is True:
               Calculates damage cost & handling fee and issues PenaltyInvoice in INR (₹).
             If impose_penalty is False:
               Admin waives the penalty with recorded exemption reason (NO invoice issued!).
        3. If all items are GOOD:
           - Clean return completed with zero fees.
        4. Transitions reservation to COMPLETED.
        """
        res = self.repo.get_reservation(reservation_id)
        if not res:
            raise ValueError(f"Reservation {reservation_id} not found")

        if res.status not in (ReservationStatus.CHECKED_OUT, ReservationStatus.RETURNED_PENDING_INSPECTION, ReservationStatus.RETURNED):
            raise ValueError(f"Reservation status must be CHECKED_OUT or RETURNED_PENDING_INSPECTION, found: {res.status.value}")

        kit = self.repo.get_kit(res.kit_id)
        if not kit:
            raise ValueError("Kit not found")

        now = datetime.now(timezone.utc)
        incident_reports = []
        invoices_issued = []
        replacements_made = []

        # Inspect each component in the kit
        for eq_type, condition in inspections.items():
            if condition in (ItemCondition.DAMAGED, ItemCondition.MISSING):
                current_item_id = kit.assigned_items.get(eq_type)
                if not current_item_id:
                    continue

                item = self.repo.get_equipment(current_item_id)
                if item:
                    item.condition = condition
                    self.repo.save_equipment(item)

                # 1. Record Incident
                note = defect_notes or f"{eq_type.value} was returned in {condition.value} state"
                incident = Incident(
                    originating_reservation_id=res.reservation_id,
                    item_id=current_item_id,
                    equipment_type=eq_type,
                    defect_description=note
                )
                self.repo.save_incident(incident)
                incident_reports.append(incident)

                # 2. College Replaces the Kit Component immediately from buffer stock
                rep_success, spare_item, rep_msg = self.replacement_service.replace_damaged_component(
                    kit_id=kit.kit_id,
                    damaged_item_id=current_item_id,
                    organizer_notes=f"Buffer stock swap for Incident {incident.incident_id} (Inspected by {inspector_name})"
                )
                if rep_success and spare_item:
                    incident.resolved_by_replacement = True
                    incident.replacement_item_id = spare_item.item_id
                    self.repo.save_incident(incident)
                    replacements_made.append({
                        "equipment_type": eq_type.value,
                        "old_damaged_item_id": current_item_id,
                        "spare_serial_number": spare_item.serial_number,
                        "status": "REPLACED_FROM_COLLEGE_STOCK",
                        "kit_is_ready": kit.is_complete_and_usable
                    })

                # 3. Assess Cost: Impose Penalty or Admin Waiver
                if impose_penalty:
                    invoice = self.billing_service.issue_damage_invoice(
                        incident_id=incident.incident_id,
                        club_id=res.club_id,
                        item_id=current_item_id,
                        equipment_type=eq_type,
                        condition=condition
                    )
                    invoices_issued.append({
                        "invoice_id": invoice.invoice_id,
                        "equipment_type": invoice.equipment_type.value,
                        "base_cost": invoice.base_cost,
                        "handling_fee": invoice.handling_fee,
                        "total_amount_due": invoice.total_amount_due,
                        "due_date": invoice.due_date.isoformat(),
                        "status": invoice.status.value
                    })

        res.status = ReservationStatus.COMPLETED
        res.inspected_at = now
        res.inspected_by = inspector_name

        total_invoiced = sum(inv["total_amount_due"] for inv in invoices_issued)
        if len(incident_reports) == 0:
            res.inspection_verdict = "CLEAN_RETURN"
            msg = "Inspection passed cleanly: All kit components intact and in GOOD condition. Zero damage detected — no penalty or invoice issued to team."
        else:
            if impose_penalty:
                res.inspection_verdict = "DEFECT_PENALTY_ISSUED"
                msg = f"Inspection recorded defects: Component replaced from college buffer stock. Damage penalty invoice of ₹{total_invoiced:,.2f} billed to team."
            else:
                res.inspection_verdict = "DEFECT_PENALTY_WAIVED"
                res.waiver_reason = waiver_reason or "Admin granted exemption / waiver"
                msg = f"Inspection recorded defects: Component replaced from college buffer stock. Admin exercised discretion to WAIVE penalty ({res.waiver_reason}). No invoice issued!"

        self.repo.save_reservation(res)

        return {
            "reservation_id": res.reservation_id,
            "return_status": "COMPLETED",
            "inspection_verdict": res.inspection_verdict,
            "inspected_by": inspector_name,
            "inspected_at": now.isoformat(),
            "has_defects": len(incident_reports) > 0,
            "damage_detected": len(incident_reports) > 0,
            "penalty_imposed": impose_penalty and len(invoices_issued) > 0,
            "waiver_reason": res.waiver_reason,
            "currency": "INR",
            "total_invoiced_inr": total_invoiced,
            "message": msg,
            "incidents": [inc.model_dump() for inc in incident_reports],
            "replacements": replacements_made,
            "invoices": invoices_issued,
            "kit_operational_status": "USABLE" if kit.is_complete_and_usable else "INCOMPLETE"
        }
