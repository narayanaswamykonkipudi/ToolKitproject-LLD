import unittest
from datetime import datetime, date, timezone, timedelta
from domain.models import (
    Student, EventKit, EquipmentItem, EquipmentType,
    ItemCondition, ItemAvailability, ClubStanding, ReservationStatus
)
from repository.memory_repo import MemoryRepository
from services.kit_replacement import KitReplacementService
from services.billing_service import PenaltyBillingService
from services.reservation_service import ReservationService
from services.availability_service import AvailabilityService
from api.routes import get_router
from api.schemas import (
    ReservationRequest, RescheduleRequest, CancelRequest,
    ReturnInspectionRequest, PaymentRequest, MaintenanceBlockRequest,
    StudentReturnSubmissionRequest, RangeAvailabilityCheckRequest
)

class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.replacement_service = KitReplacementService(self.repo)
        self.billing_service = PenaltyBillingService(self.repo)
        self.reservation_service = ReservationService(self.repo, self.replacement_service, self.billing_service)
        self.availability_service = AvailabilityService(self.repo)

        # Seed data
        self.student = self.repo.save_student(Student(
            name="Aarav Sharma",
            roll_number="STU-001",
            contact_email="aarav@campus.edu"
        ))

        cam = self.repo.save_equipment(EquipmentItem(
            equipment_type=EquipmentType.CAMERA,
            serial_number="CAM-01",
            condition=ItemCondition.GOOD,
            availability=ItemAvailability.USABLE,
            replacement_value=38000.00
        ))
        mic = self.repo.save_equipment(EquipmentItem(
            equipment_type=EquipmentType.MICROPHONE,
            serial_number="MIC-01",
            condition=ItemCondition.GOOD,
            availability=ItemAvailability.USABLE,
            replacement_value=6500.00
        ))
        tri = self.repo.save_equipment(EquipmentItem(
            equipment_type=EquipmentType.TRIPOD,
            serial_number="TRI-01",
            condition=ItemCondition.GOOD,
            availability=ItemAvailability.USABLE,
            replacement_value=3200.00
        ))

        self.kit = self.repo.save_kit(EventKit(
            name="Campus Primary Relay Kit #1",
            is_complete_and_usable=True,
            assigned_items={
                EquipmentType.CAMERA: cam.item_id,
                EquipmentType.MICROPHONE: mic.item_id,
                EquipmentType.TRIPOD: tri.item_id
            }
        ))
        cam.kit_id = self.kit.kit_id
        mic.kit_id = self.kit.kit_id
        tri.kit_id = self.kit.kit_id
        self.repo.save_equipment(cam)
        self.repo.save_equipment(mic)
        self.repo.save_equipment(tri)

        # Buffer item
        self.repo.save_equipment(EquipmentItem(
            equipment_type=EquipmentType.MICROPHONE,
            serial_number="SPARE-MIC-01",
            condition=ItemCondition.GOOD,
            availability=ItemAvailability.USABLE,
            replacement_value=6500.00,
            kit_id=None
        ))

        self.router = get_router(
            self.repo,
            self.replacement_service,
            self.billing_service,
            self.reservation_service,
            self.availability_service
        )
        self.endpoints = {route.path: route.endpoint for route in self.router.routes}

    def test_state_endpoint(self):
        fn = self.endpoints["/api/state"]
        res = fn()
        self.assertIn("students", res)
        self.assertIn("kits", res)
        self.assertEqual(len(res["students"]), 1)
        self.assertEqual(len(res["kits"]), 1)

    def test_booking_eligibility_endpoints(self):
        fn_team = self.endpoints["/api/teams/{team_id}/booking-eligibility"]
        fn_club = self.endpoints["/api/clubs/{club_id}/booking-eligibility"]
        fn_student = self.endpoints["/api/students/{student_id}/booking-eligibility"]

        sid = self.student.student_id
        res1 = fn_team(sid)
        res2 = fn_club(sid)
        res3 = fn_student(sid)

        self.assertTrue(res1["is_eligible"])
        self.assertTrue(res2["is_eligible"])
        self.assertTrue(res3["is_eligible"])

    def test_debarment_and_lifting(self):
        fn_debar = self.endpoints["/api/clubs/{club_id}/debar"]
        fn_lift = self.endpoints["/api/clubs/{club_id}/lift-debar"]
        sid = self.student.student_id

        # Debar
        res_debar = fn_debar(sid)
        self.assertTrue(res_debar["success"])
        self.assertEqual(self.student.financial_standing, ClubStanding.DEBARRED)

        # Lift debarment
        res_lift = fn_lift(sid)
        self.assertTrue(res_lift["success"])
        self.assertEqual(self.student.financial_standing, ClubStanding.GOOD_STANDING)

    def test_30_day_calendar_endpoint(self):
        fn_cal = self.endpoints["/api/availability/30-day"]
        res = fn_cal(start_date=None, kit_id=self.kit.kit_id, team_id=self.student.student_id)
        self.assertTrue(res["success"])
        self.assertEqual(len(res["days"]), 30)
        self.assertTrue(res["days"][0]["is_available"])

    def test_reservation_lifecycle_and_clean_return(self):
        fn_book = self.endpoints["/api/reservations"]
        fn_checkout = self.endpoints["/api/reservations/{reservation_id}/checkout"]
        fn_submit = self.endpoints["/api/reservations/{reservation_id}/submit-return"]
        fn_return = self.endpoints["/api/reservations/{reservation_id}/return"]

        target_date = date(2026, 10, 20)
        start_t = datetime.combine(target_date, datetime.min.time()).replace(hour=10, minute=0, tzinfo=timezone.utc)
        end_t = datetime.combine(target_date, datetime.min.time()).replace(hour=11, minute=0, tzinfo=timezone.utc)

        # Book
        req = ReservationRequest(
            club_id=self.student.student_id,
            kit_id=self.kit.kit_id,
            start_time=start_t,
            end_time=end_t
        )
        book_res = fn_book(req)
        self.assertTrue(book_res["success"])
        res_id = book_res["reservation"]["reservation_id"]

        # Checkout
        chk_res = fn_checkout(res_id)
        self.assertTrue(chk_res["success"])

        # Submit at desk
        sub_res = fn_submit(res_id, StudentReturnSubmissionRequest())
        self.assertTrue(sub_res["success"])

        # Clean return
        ret_req = ReturnInspectionRequest(
            inspections={
                EquipmentType.CAMERA: ItemCondition.GOOD,
                EquipmentType.MICROPHONE: ItemCondition.GOOD,
                EquipmentType.TRIPOD: ItemCondition.GOOD
            },
            impose_penalty=False
        )
        ret_res = fn_return(res_id, ret_req)
        self.assertTrue(ret_res["success"])
        self.assertEqual(ret_res["data"]["inspection_verdict"], "CLEAN_RETURN")
        self.assertEqual(ret_res["data"]["total_invoiced_inr"], 0.0)

if __name__ == "__main__":
    unittest.main()
