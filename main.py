import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from domain.models import (
    Student, Club, EventKit, EquipmentItem, EquipmentType, 
    ItemCondition, ItemAvailability
)
from repository.memory_repo import MemoryRepository
from services.kit_replacement import KitReplacementService
from services.billing_service import PenaltyBillingService
from services.reservation_service import ReservationService
from services.availability_service import AvailabilityService
from api.routes import get_router

app = FastAPI(title="College Event Kit Relay System - Student & Admin Implementation", version="2.0.0")

# Initialize Architecture Components
repo = MemoryRepository()
replacement_service = KitReplacementService(repo)
billing_service = PenaltyBillingService(repo)
reservation_service = ReservationService(repo, replacement_service, billing_service)
availability_service = AvailabilityService(repo)

def seed_database():
    """Initializes standard demonstration students, the single primary kit, and college buffer inventory."""
    # 1. Registered Students (Student & Admin Relay Architecture)
    s1 = repo.save_student(Student(
        name="Aarav Sharma", 
        roll_number="STU-2024-042", 
        contact_email="aarav.sharma@campus.edu"
    ))
    s2 = repo.save_student(Student(
        name="Priya Patel", 
        roll_number="STU-2024-108", 
        contact_email="priya.patel@campus.edu"
    ))
    s3 = repo.save_student(Student(
        name="Rahul Verma", 
        roll_number="STU-2024-077", 
        contact_email="rahul.verma@campus.edu"
    ))
    s4 = repo.save_student(Student(
        name="Ananya Iyer", 
        roll_number="STU-2024-019", 
        contact_email="ananya.iyer@campus.edu"
    ))

    # 2. Primary Kit Items (Single Set)
    cam = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.CAMERA,
        serial_number="CAM-ALPHA-01",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=38000.00
    ))
    mic = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.MICROPHONE,
        serial_number="MIC-STUDIO-02",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=6500.00
    ))
    tri = repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.TRIPOD,
        serial_number="TRI-PRO-03",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=3200.00
    ))

    # Single Primary Event Kit
    primary_kit = repo.save_kit(EventKit(
        name="Campus Primary Event Kit #1",
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

    # 3. College Backup Inventory Pool (College replaces broken parts from this stock)
    repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.MICROPHONE,
        serial_number="COLLEGE-BUFFER-MIC-88",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=6500.00,
        kit_id=None
    ))
    repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.CAMERA,
        serial_number="COLLEGE-BUFFER-CAM-77",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=38000.00,
        kit_id=None
    ))
    repo.save_equipment(EquipmentItem(
        equipment_type=EquipmentType.TRIPOD,
        serial_number="COLLEGE-BUFFER-TRI-66",
        condition=ItemCondition.GOOD,
        availability=ItemAvailability.USABLE,
        replacement_value=3200.00,
        kit_id=None
    ))

seed_database()

# Mount API Router
app.include_router(get_router(repo, replacement_service, billing_service, reservation_service, availability_service))

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8085))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
