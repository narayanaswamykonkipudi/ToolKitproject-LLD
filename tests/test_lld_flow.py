import sys
import os
from datetime import datetime, timezone, timedelta, date

# Set UTF-8 encoding for console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add parent directory to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from domain.models import (
    Student, StudentStanding, Club, EventKit, EquipmentItem, EquipmentType, 
    ItemCondition, ItemAvailability, ClubStanding, SlotState
)
from repository.memory_repo import MemoryRepository
from services.kit_replacement import KitReplacementService
from services.billing_service import PenaltyBillingService
from services.reservation_service import ReservationService
from services.availability_service import AvailabilityService

def test_complete_lld_flow():
    print("==========================================================")
    print(" COLLEGE EVENT KIT RELAY SYSTEM — COMPREHENSIVE LLD FLOW ")
    print("==========================================================")

    repo = MemoryRepository()
    replacement_service = KitReplacementService(repo)
    billing_service = PenaltyBillingService(repo)
    reservation_service = ReservationService(repo, replacement_service, billing_service)
    availability_service = AvailabilityService(repo)

    # 1. Setup Base Data in Indian Rupees (INR / ₹) - Registered Students & Single Kit
    student_a = repo.save_student(Student(name="Aarav Sharma", roll_number="STU-2024-001", contact_email="aarav@campus.edu"))
    student_b = repo.save_student(Student(name="Priya Patel", roll_number="STU-2024-002", contact_email="priya@campus.edu"))
    club_a = student_a
    club_b = student_b

    cam = repo.save_equipment(EquipmentItem(equipment_type=EquipmentType.CAMERA, serial_number="CAM-01", replacement_value=38000.00))
    mic = repo.save_equipment(EquipmentItem(equipment_type=EquipmentType.MICROPHONE, serial_number="MIC-01", replacement_value=6500.00))
    tri = repo.save_equipment(EquipmentItem(equipment_type=EquipmentType.TRIPOD, serial_number="TRI-01", replacement_value=3200.00))

    primary_kit = repo.save_kit(EventKit(
        name="Primary Kit #1",
        is_complete_and_usable=True,
        assigned_items={
            EquipmentType.CAMERA: cam.item_id,
            EquipmentType.MICROPHONE: mic.item_id,
            EquipmentType.TRIPOD: tri.item_id
        }
    ))
    cam.kit_id = primary_kit.kit_id
    mic.kit_id = primary_kit.kit_id
    tri.kit_id = primary_kit.kit_id
    repo.save_equipment(cam)
    repo.save_equipment(mic)
    repo.save_equipment(tri)

    # Spare components in college buffer
    spare_mic = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.MICROPHONE,
        serial_number="COLLEGE-SPARE-MIC-999",
        replacement_value=6500.00,
        kit_id=None
    ))
    spare_cam = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.CAMERA,
        serial_number="COLLEGE-SPARE-CAM-888",
        replacement_value=38000.00,
        kit_id=None
    ))
    spare_tri = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.TRIPOD,
        serial_number="COLLEGE-SPARE-TRI-777",
        replacement_value=3200.00,
        kit_id=None
    ))

    target_date = date(2026, 10, 15)
    t9 = datetime.combine(target_date, datetime.min.time()).replace(hour=9, minute=0, tzinfo=timezone.utc)
    t10 = datetime.combine(target_date, datetime.min.time()).replace(hour=10, minute=0, tzinfo=timezone.utc)
    t10_10 = datetime.combine(target_date, datetime.min.time()).replace(hour=10, minute=10, tzinfo=timezone.utc)
    t10_15 = datetime.combine(target_date, datetime.min.time()).replace(hour=10, minute=15, tzinfo=timezone.utc)
    t11 = datetime.combine(target_date, datetime.min.time()).replace(hour=11, minute=0, tzinfo=timezone.utc)
    t11_15 = datetime.combine(target_date, datetime.min.time()).replace(hour=11, minute=15, tzinfo=timezone.utc)
    t12 = datetime.combine(target_date, datetime.min.time()).replace(hour=12, minute=0, tzinfo=timezone.utc)
    t13 = datetime.combine(target_date, datetime.min.time()).replace(hour=13, minute=0, tzinfo=timezone.utc)
    t14 = datetime.combine(target_date, datetime.min.time()).replace(hour=14, minute=0, tzinfo=timezone.utc)

    # --- STEP 1: Check Initial Availability ---
    print("\n--- STEP 1: Availability Service Check ---")
    slots = availability_service.get_available_slots(target_date, duration_minutes=60, club_id=club_a.club_id, kit_id=primary_kit.kit_id)
    print(f"Generated {len(slots)} candidate slots for {target_date.isoformat()}.")
    assert len(slots) > 0
    assert slots[0].state == SlotState.AVAILABLE

    # --- STEP 2: Student Aarav Books Slot (09:00 - 10:00) ---
    print("\n--- STEP 2: Student Aarav Books Slot (09:00 - 10:00) ---")
    ok, res1, msg1 = reservation_service.create_reservation(student_a.student_id, primary_kit.kit_id, t9, t10)
    assert ok is True
    print(f"Success: {msg1}")

    # --- STEP 3: Club B Requests (10:10 - 11:00) -> Gap Buffer Test ---
    print("\n--- STEP 3: Club B Requests (10:10 - 11:00) -> Gap Buffer Test ---")
    ok, res2, msg2 = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, t10_10, t11)
    assert ok is False
    print(f"Correctly Rejected: {msg2}")

    # --- STEP 4: Club B Requests (10:15 - 11:15) -> Compliant Gap ---
    print("\n--- STEP 4: Club B Requests (10:15 - 11:15) -> Compliant Gap ---")
    ok, res2, msg2 = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, t10_15, t11_15)
    assert ok is True
    print(f"Success: {msg2}")

    # --- STEP 5: Maintenance Block Test (13:00 - 14:00) ---
    print("\n--- STEP 5: Admin Creates Maintenance Block (13:00 - 14:00) ---")
    m_block = availability_service.create_maintenance_block(primary_kit.kit_id, t13, t14, "Annual Sensor Calibration")
    ok, res_m, msg_m = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, t13, t14)
    assert ok is False
    print(f"Correctly Rejected by Maintenance Block: {msg_m}")

    # --- STEP 6: Reschedule Test ---
    print("\n--- STEP 6: Club B Reschedules Slot (10:15-11:15) -> Conflicting Slot -> Fails Safely ---")
    ok_r, res_r, msg_r = reservation_service.reschedule_reservation(res2.reservation_id, t9, t10)
    assert ok_r is False
    assert res2.status == "CONFIRMED"
    print(f"Reschedule Conflict Safely Handled: {msg_r}")

    # --- STEP 7: Club A Checkout & Return with Damaged Microphone ---
    print("\n--- STEP 7: Club A Checkout & Return with Damaged Microphone ---")
    ok_co, msg_co = reservation_service.checkout_kit(res1.reservation_id)
    assert ok_co is True
    print(f"Checkout: {msg_co}")

    return_result = reservation_service.process_return(
        res1.reservation_id,
        inspections={EquipmentType.MICROPHONE: ItemCondition.DAMAGED},
        defect_notes="Microphone diaphragm cracked during stage performance"
    )
    print(f"Return Processed! Kit Usability: {return_result['kit_operational_status']}")
    assert return_result["kit_operational_status"] == "USABLE"
    assert return_result["has_defects"] is True
    assert len(return_result["invoices"]) == 1
    # Damaged Mic: Repair ₹700 + 15% (₹105) = ₹805.00
    assert return_result["invoices"][0]["total_amount_due"] == 805.00
    print(f"Damage Invoice in Indian Rupees (₹): {return_result['invoices'][0]['total_amount_due']}")

    # --- STEP 8: Verify Team A Debarment in INR & Club B Unaffected Usage ---
    print("\n--- STEP 8: Verify Team A Debarment & Club B Unaffected Usage ---")
    # Simulate payment due date expiration for Club A
    for inv in repo.list_invoices():
        inv.due_date = datetime.now(timezone.utc) - timedelta(days=1)
        repo.save_invoice(inv)
    billing_service.trigger_overdue_check()

    # Club A attempts new booking -> DEBARRED
    t14_15 = t14 + timedelta(minutes=15)
    t15_15 = t14_15 + timedelta(hours=1)
    ok_a2, res_a2, msg_a2 = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, t14_15, t15_15)
    assert ok_a2 is False
    assert "₹805.00" in msg_a2
    print(f"Team A Booking Restriction Enforced (in INR): {msg_a2}")

    # Club B performs checkout on replaced kit -> Allowed!
    ok_b_co, msg_b_co = reservation_service.checkout_kit(res2.reservation_id)
    assert ok_b_co is True
    print(f"Club B Handover Status: {msg_b_co}")

    # --- STEP 9: Settlement in INR & Eligibility Restoration ---
    print("\n--- STEP 9: Club A Settles Invoice -> Eligibility Restored ---")
    inv_id = return_result["invoices"][0]["invoice_id"]
    ok_pay, txn, msg_pay = billing_service.process_payment(inv_id)
    assert ok_pay is True
    assert "₹805.00" in msg_pay
    print(f"Payment Result (INR): {msg_pay}")

    # Club A books again -> Allowed!
    ok_a3, res_a3, msg_a3 = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, t14_15, t15_15)
    assert ok_a3 is True
    print(f"Club A Access Restored: {msg_a3}")

    # --- STEP 10: Club B Returns Kit in 100% GOOD Condition -> NO INVOICE ISSUED ---
    print("\n--- STEP 10: Club B Returns Kit Intact -> No Damage, NO Invoice Issued ---")
    club_b_before_balance = repo.get_club(club_b.club_id).outstanding_balance
    return_result_b = reservation_service.process_return(
        res2.reservation_id,
        inspections={
            EquipmentType.CAMERA: ItemCondition.GOOD,
            EquipmentType.MICROPHONE: ItemCondition.GOOD,
            EquipmentType.TRIPOD: ItemCondition.GOOD
        },
        defect_notes="All items in pristine condition."
    )
    assert return_result_b["has_defects"] is False
    assert len(return_result_b["invoices"]) == 0
    assert len(return_result_b["incidents"]) == 0
    club_b_after_balance = repo.get_club(club_b.club_id).outstanding_balance
    assert club_b_after_balance == club_b_before_balance
    print(f"Clean Return Verified: {return_result_b['message']}")
    print(f"Club B Balance unchanged: ₹{club_b_after_balance:.2f}, Invoices issued: {len(return_result_b['invoices'])}")

    # --- STEP 11: Validation Verification (Timing, Dates, Accounts, Payments) ---
    print("\n--- STEP 11: Timing, Operating Hours & Payment Validations ---")
    # Test past time slot
    past_st = datetime.now(timezone.utc) - timedelta(hours=3)
    past_et = past_st + timedelta(hours=1)
    ok_past, _, msg_past = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, past_st, past_et)
    assert ok_past is False
    print(f"Past slot correctly blocked: {msg_past}")

    # Test outside operating hours (e.g. 07:00 AM)
    t7 = datetime.combine(target_date, datetime.min.time()).replace(hour=7, minute=0, tzinfo=timezone.utc)
    t8 = datetime.combine(target_date, datetime.min.time()).replace(hour=8, minute=0, tzinfo=timezone.utc)
    ok_early, _, msg_early = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, t7, t8)
    assert ok_early is False
    print(f"Outside operating hours blocked: {msg_early}")

    # Test duration < 15 minutes
    t_short_end = t14_15 + timedelta(minutes=5)
    ok_short, _, msg_short = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, t14_15, t_short_end)
    assert ok_short is False
    print(f"Short duration (<15m) blocked: {msg_short}")

    # Test payment validations
    ok_neg, _, msg_neg = billing_service.process_payment(inv_id, -100.0)
    assert ok_neg is False
    print(f"Invalid payment blocked: {msg_neg}")

    # --- STEP 12: Multi-Day Booking by Days & Instant Debarment on Defect ---
    print("\n--- STEP 12: Multi-Day Booking by Days & Immediate Penalty Debarment ---")
    multi_start = datetime.combine(target_date + timedelta(days=2), datetime.min.time()).replace(hour=9, minute=0, tzinfo=timezone.utc)
    multi_end = datetime.combine(target_date + timedelta(days=4), datetime.min.time()).replace(hour=17, minute=0, tzinfo=timezone.utc) # 3 full days
    
    # Club B books for 3 days
    ok_multi, res_multi, msg_multi = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, multi_start, multi_end)
    assert ok_multi is True
    print(f"Multi-day booking success (3 days): {msg_multi}")

    # Club A attempts to book an intermediate slot within Club B's multi-day booking -> BLOCKED
    mid_start = datetime.combine(target_date + timedelta(days=3), datetime.min.time()).replace(hour=10, minute=0, tzinfo=timezone.utc)
    mid_end = datetime.combine(target_date + timedelta(days=3), datetime.min.time()).replace(hour=12, minute=0, tzinfo=timezone.utc)
    ok_conflict, _, msg_conflict = reservation_service.create_reservation(club_a.club_id, primary_kit.kit_id, mid_start, mid_end)
    assert ok_conflict is False
    print(f"Intermediate conflict inside multi-day correctly blocked: {msg_conflict}")

    # Club B checkouts kit
    ok_co2, _ = reservation_service.checkout_kit(res_multi.reservation_id)
    assert ok_co2 is True

    # Return with Tripod Defect: Admin imposes penalty
    return_result_defect = reservation_service.process_return(
        res_multi.reservation_id,
        inspections={
            EquipmentType.CAMERA: ItemCondition.GOOD,
            EquipmentType.MICROPHONE: ItemCondition.GOOD,
            EquipmentType.TRIPOD: ItemCondition.DAMAGED
        },
        defect_notes="Tripod fluid head clamp stripped"
    )
    assert return_result_defect["has_defects"] is True
    assert len(return_result_defect["invoices"]) == 1
    # Tripod damaged: Base ₹450 + 15% (min ₹100 surcharge) = ₹550.00
    tripod_fee = return_result_defect["invoices"][0]["total_amount_due"]
    assert tripod_fee == 550.00
    print(f"Admin imposed penalty of ₹{tripod_fee:.2f} on Club B")

    # Verify Club B is IMMEDIATELY DEBARRED and cannot book any new slots!
    future_start = datetime.combine(target_date + timedelta(days=6), datetime.min.time()).replace(hour=10, minute=0, tzinfo=timezone.utc)
    future_end = datetime.combine(target_date + timedelta(days=6), datetime.min.time()).replace(hour=12, minute=0, tzinfo=timezone.utc)
    ok_b_blocked, _, msg_b_blocked = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, future_start, future_end)
    assert ok_b_blocked is False
    assert "₹550.00" in msg_b_blocked
    print(f"Club B immediately blocked from booking due to unsettled penalty: {msg_b_blocked}")

    # Club B clears payment in full
    tripod_inv_id = return_result_defect["invoices"][0]["invoice_id"]
    ok_settled, _, msg_settled = billing_service.process_payment(tripod_inv_id)
    assert ok_settled is True
    print(f"Club B settled payment: {msg_settled}")

    # Now Club B CAN book again!
    ok_b_unblocked, res_b_new, msg_b_unblocked = reservation_service.create_reservation(club_b.club_id, primary_kit.kit_id, future_start, future_end)
    assert ok_b_unblocked is True
    print(f"Club B can book again after payment cleared: {msg_b_unblocked}")

    # Test Manual Admin Debarment & Lifting (Restoration)
    billing_service.mark_club_debarred(club_a.club_id)
    assert club_a.financial_standing == ClubStanding.DEBARRED
    billing_service.lift_club_debarment(club_a.club_id)
    assert club_a.financial_standing == ClubStanding.GOOD_STANDING

    print("\n>>> ALL INTEGRATED LLD INVARIANTS & VALIDATIONS TESTED & VERIFIED SUCCESSFULLY! <<<\n")

import unittest
class TestLLDFlow(unittest.TestCase):
    def test_complete_flow(self):
        test_complete_lld_flow()

if __name__ == "__main__":
    test_complete_lld_flow()
