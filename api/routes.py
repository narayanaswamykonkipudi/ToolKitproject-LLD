from datetime import datetime, date, timezone
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, Optional, List
from domain.models import EquipmentType, ItemCondition, ClubStanding, ReservationStatus
from repository.memory_repo import MemoryRepository
from services.kit_replacement import KitReplacementService
from services.billing_service import PenaltyBillingService
from services.reservation_service import ReservationService
from services.availability_service import AvailabilityService
from api.schemas import (
    ReservationRequest, RescheduleRequest, CancelRequest, 
    ReturnInspectionRequest, PaymentRequest, MaintenanceBlockRequest,
    StudentReturnSubmissionRequest, RangeAvailabilityCheckRequest
)

def get_router(
    repo: MemoryRepository,
    replacement_service: KitReplacementService,
    billing_service: PenaltyBillingService,
    reservation_service: ReservationService,
    availability_service: AvailabilityService
) -> APIRouter:
    router = APIRouter(prefix="/api")

    # ==========================================
    # SYSTEM STATE & SHARED DATA
    # ==========================================
    @router.get("/state")
    def get_system_state() -> Dict[str, Any]:
        """Returns the complete live state of the system."""
        kits = repo.list_kits()
        student_list = [s.model_dump() for s in repo.list_students()]
        return {
            "students": student_list,
            "clubs": student_list,  # compatibility alias
            "kits": [k.model_dump() for k in kits],
            "equipment": [e.model_dump() for e in repo.list_equipment()],
            "reservations": [r.model_dump() for r in repo.list_reservations()],
            "invoices": [i.model_dump() for i in repo.list_invoices()],
            "maintenance_blocks": [m.model_dump() for m in repo.list_maintenance_blocks()],
            "booking_restrictions": [br.model_dump() for br in repo.list_booking_restrictions()],
            "replacement_logs": [log.model_dump() for log in repo.list_replacement_logs()],
            "payments": [p.model_dump() for p in repo.list_payments()]
        }

    # ==========================================
    # USER MODULE ENDPOINTS (Student Teams)
    # ==========================================
    @router.get("/user/reservations")
    def get_user_reservations(team_id: str = Query(..., alias="team_id")):
        """Returns reservations specific to a student team."""
        reservations = [r for r in repo.list_reservations() if r.club_id == team_id]
        return {"success": True, "reservations": [r.model_dump() for r in reservations]}

    @router.get("/availability")
    def get_available_slots(
        date_str: Optional[str] = Query(None, alias="date"),
        duration: int = Query(60, ge=15, le=480),
        team_id: Optional[str] = Query(None, alias="team_id"),
        kit_id: Optional[str] = Query(None, alias="kit_id")
    ):
        """Finds available time slots considering operating hours, 15-min gap, kit condition, maintenance, and team standing."""
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

        slots = availability_service.get_available_slots(
            target_date=target_date,
            duration_minutes=duration,
            club_id=team_id,
            kit_id=kit_id
        )
        return {"success": True, "date": target_date.isoformat(), "duration_minutes": duration, "slots": [s.model_dump() for s in slots]}

    @router.post("/availability/check-range")
    def check_range_availability(payload: RangeAvailabilityCheckRequest):
        """Checks if a multi-day or custom time slot is available for booking without conflicts or blocks."""
        from domain.models import ensure_utc
        start_time = ensure_utc(payload.start_time)
        end_time = ensure_utc(payload.end_time)
        
        kit_id = payload.kit_id
        if not kit_id:
            kits = repo.list_kits()
            if not kits:
                raise HTTPException(status_code=400, detail="No active kits available")
            kit_id = kits[0].kit_id

        # Use reservation service pipeline
        validation = reservation_service.pipeline.validate(
            repo=repo,
            club_id=payload.club_id or "",
            kit_id=kit_id,
            start_time=start_time,
            end_time=end_time
        )
        return {
            "success": True,
            "is_available": validation.is_allowed,
            "reason": validation.rejection_reason if not validation.is_allowed else "Selected time slot/days are fully available for reservation.",
            "restriction_code": validation.restriction_code
        }

    @router.post("/reservations")
    def create_reservation(payload: ReservationRequest):
        """Creates a booking or blocks debarred clubs / unavailable slots."""
        ok, res, msg = reservation_service.create_reservation(
            club_id=payload.club_id,
            kit_id=payload.kit_id,
            start_time=payload.start_time,
            end_time=payload.end_time
        )
        if not ok:
            if "Restricted" in msg or "DEBARRED" in msg or "RESTRICTED" in msg:
                raise HTTPException(status_code=403, detail=msg)
            elif "conflict" in msg.lower() or "gap" in msg.lower():
                raise HTTPException(status_code=409, detail=msg)
            else:
                raise HTTPException(status_code=400, detail=msg)

        return {"success": True, "message": msg, "reservation": res.model_dump()}

    @router.get("/reservations/{reservation_id}")
    def get_reservation_details(reservation_id: str):
        """View booking details."""
        res = repo.get_reservation(reservation_id)
        if not res:
            raise HTTPException(status_code=404, detail="Reservation not found")
        club = repo.get_club(res.club_id)
        kit = repo.get_kit(res.kit_id)
        return {
            "success": True, 
            "reservation": res.model_dump(), 
            "club": club.model_dump() if club else None, 
            "kit": kit.model_dump() if kit else None
        }

    @router.patch("/reservations/{reservation_id}/reschedule")
    def reschedule_reservation(reservation_id: str, payload: RescheduleRequest):
        """Reschedules a confirmed booking atomically."""
        ok, res, msg = reservation_service.reschedule_reservation(
            reservation_id=reservation_id,
            new_start_time=payload.new_start_time,
            new_end_time=payload.new_end_time
        )
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        return {"success": True, "message": msg, "reservation": res.model_dump() if res else None}

    @router.post("/reservations/{reservation_id}/cancel")
    def cancel_reservation(reservation_id: str, payload: CancelRequest = CancelRequest()):
        """Cancels a booking and releases the slot window."""
        ok, msg = reservation_service.cancel_reservation(reservation_id, payload.reason or "User cancelled")
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/reservations/{reservation_id}/checkout")
    def checkout_reservation(reservation_id: str):
        """Student collects ('takes') the kit after pre-handover validation."""
        ok, msg = reservation_service.checkout_kit(reservation_id)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/reservations/{reservation_id}/submit-return")
    def student_submit_return(reservation_id: str, payload: StudentReturnSubmissionRequest = StudentReturnSubmissionRequest()):
        """Student group submits the kit back to desk, queueing it for Admin inspection."""
        ok, msg = reservation_service.submit_return_by_student(reservation_id, payload.student_notes)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg}

    @router.post("/reservations/{reservation_id}/return")
    def return_reservation(reservation_id: str, payload: ReturnInspectionRequest):
        """Admin conducts official physical inspection, records defective items, and imposes penalty if damage occurred."""
        try:
            result = reservation_service.process_return(
                reservation_id=reservation_id,
                inspections=payload.inspections,
                defect_notes=payload.defect_notes,
                impose_penalty=payload.impose_penalty,
                waiver_reason=payload.waiver_reason,
                inspector_name=payload.inspector_name or "College Administrator"
            )
            return {"success": True, "data": result}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/teams/{team_id}/booking-eligibility")
    def check_team_booking_eligibility(team_id: str):
        """Checks whether a team is eligible to make a new booking."""
        club = repo.get_club(team_id)
        if not club:
            raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

        invoices = repo.get_invoices_by_club(team_id)
        overdue_invoices = [i for i in invoices if i.status.value == "OVERDUE"]
        unpaid_invoices = [i for i in invoices if i.status.value in ("ISSUED", "OVERDUE")]

        is_restricted = (club.financial_standing in (ClubStanding.DEBARRED, ClubStanding.PENDING_PAYMENT) or club.outstanding_balance > 0 or len(overdue_invoices) > 0)
        reason = None
        if is_restricted:
            reason = f"Team '{club.name}' is DEBARRED due to ₹{club.outstanding_balance:,.2f} outstanding damage penalties. Clear dues in the portal to unblock access."
        else:
            reason = f"Team '{club.name}' is in GOOD STANDING and eligible for new bookings."

        return {
            "success": True,
            "team_id": club.club_id,
            "team_name": club.name,
            "is_eligible": not is_restricted,
            "financial_standing": club.financial_standing.value,
            "outstanding_balance": club.outstanding_balance,
            "unpaid_claims_count": len(unpaid_invoices),
            "overdue_claims_count": len(overdue_invoices),
            "message": reason
        }

    @router.get("/clubs/{club_id}/billing")
    def get_club_billing_data(club_id: str):
        """Returns detailed payment-related data, invoices, and restriction status for the team."""
        try:
            data = billing_service.get_payment_related_data(club_id)
            return {"success": True, "billing_data": data}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/invoices/{invoice_id}/pay")
    def pay_invoice(invoice_id: str, payload: PaymentRequest = PaymentRequest()):
        """Student settles damage liability invoice and clears club debarment."""
        ok, txn, msg = billing_service.process_payment(invoice_id, payload.amount)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"success": True, "message": msg, "transaction": txn.model_dump() if txn else None}

    # ==========================================
    # ADMIN MODULE ENDPOINTS (College Organizer)
    # ==========================================
    @router.get("/kits/{kit_id}/calendar")
    def get_kit_calendar(
        kit_id: str,
        from_str: Optional[str] = Query(None, alias="from"),
        to_str: Optional[str] = Query(None, alias="to")
    ):
        """Returns consolidated booking calendar with reservations, buffers, and maintenance blocks."""
        now = datetime.now(timezone.utc)
        from_dt = datetime.fromisoformat(from_str) if from_str else now.replace(hour=0, minute=0, second=0)
        to_dt = datetime.fromisoformat(to_str) if to_str else from_dt.replace(hour=23, minute=59, second=59)

        timeline = availability_service.get_kit_calendar(kit_id, from_dt, to_dt)
        return {"success": True, "kit_id": kit_id, "timeline": timeline}

    @router.get("/admin/calendar")
    def get_admin_calendar():
        """View all reservations, buffers, and operational blocks across the system."""
        kits = repo.list_kits()
        if not kits:
            return {"success": True, "timeline": []}
        now = datetime.now(timezone.utc)
        from_dt = now.replace(hour=0, minute=0, second=0)
        to_dt = now.replace(hour=23, minute=59, second=59)
        timeline = availability_service.get_kit_calendar(kits[0].kit_id, from_dt, to_dt)
        return {"success": True, "timeline": timeline}

    @router.post("/kits/{kit_id}/maintenance-blocks")
    def create_maintenance_block(kit_id: str, payload: MaintenanceBlockRequest):
        """Admin schedules a maintenance/calibration block on the kit."""
        block = availability_service.create_maintenance_block(
            kit_id=kit_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            reason=payload.reason,
            created_by=payload.created_by or "College Administrator"
        )
        return {"success": True, "message": "Maintenance block created", "block": block.model_dump()}

    @router.post("/admin/trigger-overdue")
    def trigger_overdue_check():
        """Admin audits due dates: scans for expired claims and debars defaulting teams."""
        overdue_list = billing_service.trigger_overdue_check()
        return {
            "success": True, 
            "overdue_count": len(overdue_list), 
            "message": f"Audit complete. Processed {len(overdue_list)} overdue claims; teams transitioned to DEBARRED."
        }

    @router.get("/clubs/{club_id}/booking-eligibility")
    def check_club_booking_eligibility(club_id: str):
        return check_team_booking_eligibility(club_id)

    @router.get("/students/{student_id}/billing")
    def get_student_billing_data(student_id: str):
        return get_club_billing_data(student_id)

    @router.get("/students/{student_id}/booking-eligibility")
    def check_student_booking_eligibility(student_id: str):
        return check_team_booking_eligibility(student_id)

    @router.post("/students/{student_id}/debar")
    def toggle_student_debarment(student_id: str):
        return toggle_debarment(student_id)

    @router.post("/clubs/{club_id}/debar")
    def toggle_debarment(club_id: str):
        """Admin explicitly sets or tests debarment on a student."""
        try:
            club = billing_service.mark_club_debarred(club_id)
            return {"success": True, "message": f"Student {club.name} is now DEBARRED", "club": club.model_dump(), "student": club.model_dump()}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/clubs/{club_id}/lift-debar")
    def lift_debarment_route(club_id: str):
        """Admin lifts debarment on a student who has cleared their dues."""
        try:
            club = billing_service.lift_club_debarment(club_id)
            return {"success": True, "message": f"Student {club.name} standing restored to GOOD STANDING", "club": club.model_dump(), "student": club.model_dump()}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/students/{student_id}/lift-debar")
    def lift_student_debarment_route(student_id: str):
        return lift_debarment_route(student_id)

    @router.get("/availability/30-day")
    def get_30_day_calendar(
        start_date: Optional[str] = Query(None, alias="start_date"),
        kit_id: Optional[str] = Query(None, alias="kit_id"),
        team_id: Optional[str] = Query(None, alias="team_id")
    ):
        """Returns 30-day rolling calendar availability matrix."""
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        matrix = availability_service.get_30_day_availability(start_date=s_date, kit_id=kit_id, club_id=team_id)
        return {"success": True, "days": matrix}

    return router
