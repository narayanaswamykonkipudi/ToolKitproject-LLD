from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel
from domain.models import EquipmentType, ItemCondition

class ReservationRequest(BaseModel):
    club_id: str
    kit_id: Optional[str] = None
    start_time: datetime
    end_time: datetime

class RescheduleRequest(BaseModel):
    new_start_time: datetime
    new_end_time: datetime

class CancelRequest(BaseModel):
    reason: Optional[str] = "User requested cancellation"

class StudentReturnSubmissionRequest(BaseModel):
    student_notes: Optional[str] = "Kit physical handover at campus equipment counter"

class AdminInspectionRequest(BaseModel):
    inspections: Dict[EquipmentType, ItemCondition]
    defect_notes: Optional[str] = None
    impose_penalty: bool = True
    waiver_reason: Optional[str] = None
    inspector_name: Optional[str] = "College Administrator"

class ReturnInspectionRequest(BaseModel):
    inspections: Dict[EquipmentType, ItemCondition]
    defect_notes: Optional[str] = None
    impose_penalty: bool = True
    waiver_reason: Optional[str] = None
    inspector_name: Optional[str] = "College Administrator"

class RangeAvailabilityCheckRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    kit_id: Optional[str] = None
    club_id: Optional[str] = None

class PaymentRequest(BaseModel):
    amount: Optional[float] = None

class MaintenanceBlockRequest(BaseModel):
    kit_id: str
    start_time: datetime
    end_time: datetime
    reason: str
    created_by: Optional[str] = "College Administrator"
