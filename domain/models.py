from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import uuid

def generate_uuid() -> str:
    return str(uuid.uuid4())

def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class EquipmentType(str, Enum):
    CAMERA = "CAMERA"
    MICROPHONE = "MICROPHONE"
    TRIPOD = "TRIPOD"

class ItemCondition(str, Enum):
    GOOD = "GOOD"
    DAMAGED = "DAMAGED"
    MISSING = "MISSING"

class ItemAvailability(str, Enum):
    USABLE = "USABLE"
    UNDER_REPAIR = "UNDER_REPAIR"
    LOST = "LOST"

class StudentStanding(str, Enum):
    GOOD_STANDING = "GOOD_STANDING"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    DEBARRED = "DEBARRED"

ClubStanding = StudentStanding  # Backwards compatibility alias

class ReservationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CHECKED_OUT = "CHECKED_OUT"
    RETURNED_PENDING_INSPECTION = "RETURNED_PENDING_INSPECTION"
    RETURNED = "RETURNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class InvoiceStatus(str, Enum):
    ISSUED = "ISSUED"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    WAIVED = "WAIVED"

class PaymentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class SlotState(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    INSPECTION_BUFFER = "INSPECTION_BUFFER"
    MAINTENANCE_BLOCKED = "MAINTENANCE_BLOCKED"
    EQUIPMENT_BLOCKED = "EQUIPMENT_BLOCKED"
    OUTSIDE_OPERATING_HOURS = "OUTSIDE_OPERATING_HOURS"

class EquipmentItem(BaseModel):
    item_id: str = Field(default_factory=generate_uuid)
    kit_id: Optional[str] = None  # None if in college buffer stock
    equipment_type: EquipmentType
    serial_number: str
    condition: ItemCondition = ItemCondition.GOOD
    availability: ItemAvailability = ItemAvailability.USABLE
    replacement_value: float

class EventKit(BaseModel):
    kit_id: str = Field(default_factory=generate_uuid)
    name: str = "Campus Primary Relay Kit #1"
    is_complete_and_usable: bool = True
    assigned_items: Dict[EquipmentType, str] = Field(default_factory=dict)  # EquipmentType -> item_id

class Student(BaseModel):
    student_id: str = Field(default_factory=generate_uuid)
    name: str
    roll_number: Optional[str] = None
    contact_email: str
    financial_standing: StudentStanding = StudentStanding.GOOD_STANDING
    outstanding_balance: float = 0.0

    @property
    def club_id(self) -> str:
        return self.student_id

Club = Student  # Backwards compatibility alias

class MaintenanceBlock(BaseModel):
    block_id: str = Field(default_factory=generate_uuid)
    kit_id: str
    start_time: datetime
    end_time: datetime
    reason: str
    created_by: str = "College Administrator"
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BookingRestriction(BaseModel):
    restriction_id: str = Field(default_factory=generate_uuid)
    student_id: Optional[str] = None
    club_id: Optional[str] = None
    reason: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    is_active: bool = True

    def model_post_init(self, __context: Any) -> None:
        if not self.club_id and self.student_id:
            self.club_id = self.student_id
        elif not self.student_id and self.club_id:
            self.student_id = self.club_id

class Reservation(BaseModel):
    reservation_id: str = Field(default_factory=generate_uuid)
    student_id: Optional[str] = None
    club_id: Optional[str] = None
    kit_id: str
    start_time: datetime
    end_time: datetime
    status: ReservationStatus = ReservationStatus.CONFIRMED
    rescheduled_from_id: Optional[str] = None
    cancellation_reason: Optional[str] = None
    returned_at: Optional[datetime] = None
    inspected_at: Optional[datetime] = None
    inspected_by: Optional[str] = None
    inspection_verdict: Optional[str] = None
    waiver_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: Any) -> None:
        if not self.club_id and self.student_id:
            self.club_id = self.student_id
        elif not self.student_id and self.club_id:
            self.student_id = self.club_id

class TimeSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    state: SlotState
    reason: str
    reservation_id: Optional[str] = None
    block_id: Optional[str] = None

class Incident(BaseModel):
    incident_id: str = Field(default_factory=generate_uuid)
    originating_reservation_id: str
    item_id: str
    equipment_type: EquipmentType
    defect_description: str
    reported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_by_replacement: bool = False
    replacement_item_id: Optional[str] = None

class PenaltyInvoice(BaseModel):
    invoice_id: str = Field(default_factory=generate_uuid)
    incident_id: str
    student_id: Optional[str] = None
    club_id: Optional[str] = None
    item_id: str
    equipment_type: EquipmentType
    base_cost: float
    handling_fee: float
    total_amount_due: float
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    status: InvoiceStatus = InvoiceStatus.ISSUED
    paid_at: Optional[datetime] = None
    transaction_ref: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.club_id and self.student_id:
            self.club_id = self.student_id
        elif not self.student_id and self.club_id:
            self.student_id = self.club_id

class PaymentTransaction(BaseModel):
    transaction_id: str = Field(default_factory=generate_uuid)
    invoice_id: str
    student_id: Optional[str] = None
    club_id: Optional[str] = None
    amount_paid: float
    payment_method: str = "ONLINE_COLLEGE_PORTAL"
    reference_id: str = Field(default_factory=generate_uuid)
    paid_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: PaymentStatus = PaymentStatus.SUCCESS

    def model_post_init(self, __context: Any) -> None:
        if not self.club_id and self.student_id:
            self.club_id = self.student_id
        elif not self.student_id and self.club_id:
            self.student_id = self.club_id

class ReplacementLog(BaseModel):
    log_id: str = Field(default_factory=generate_uuid)
    kit_id: str
    damaged_item_id: str
    replacement_item_id: str
    equipment_type: EquipmentType
    replaced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    organizer_notes: str
