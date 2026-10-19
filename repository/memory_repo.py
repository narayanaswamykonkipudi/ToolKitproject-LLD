import threading
from typing import Dict, List, Optional
from domain.models import (
    Club, EventKit, EquipmentItem, EquipmentType, 
    Reservation, Incident, PenaltyInvoice, PaymentTransaction, 
    ReplacementLog, MaintenanceBlock, BookingRestriction,
    ItemCondition, ItemAvailability, ClubStanding
)

class MemoryRepository:
    """Thread-safe in-memory data store for the Event Kit Relay System."""
    
    def __init__(self):
        self._lock = threading.RLock()
        self.clubs: Dict[str, Club] = {}
        self.kits: Dict[str, EventKit] = {}
        self.equipment: Dict[str, EquipmentItem] = {}
        self.reservations: Dict[str, Reservation] = {}
        self.incidents: Dict[str, Incident] = {}
        self.invoices: Dict[str, PenaltyInvoice] = {}
        self.payments: Dict[str, PaymentTransaction] = {}
        self.replacement_logs: List[ReplacementLog] = []
        self.maintenance_blocks: Dict[str, MaintenanceBlock] = {}
        self.booking_restrictions: Dict[str, BookingRestriction] = {}

    # --- Student & Club Operations ---
    def save_student(self, student: Club) -> Club:
        with self._lock:
            sid = getattr(student, "student_id", None) or getattr(student, "club_id", None)
            self.clubs[sid] = student
            return student

    def get_student(self, student_id: str) -> Optional[Club]:
        with self._lock:
            return self.clubs.get(student_id)

    def list_students(self) -> List[Club]:
        with self._lock:
            return list(self.clubs.values())

    save_club = save_student
    get_club = get_student
    list_clubs = list_students

    # --- Equipment & Kit Operations ---
    def save_kit(self, kit: EventKit) -> EventKit:
        with self._lock:
            self.kits[kit.kit_id] = kit
            return kit

    def get_kit(self, kit_id: str) -> Optional[EventKit]:
        with self._lock:
            return self.kits.get(kit_id)

    def list_kits(self) -> List[EventKit]:
        with self._lock:
            return list(self.kits.values())

    def save_equipment(self, item: EquipmentItem) -> EquipmentItem:
        with self._lock:
            self.equipment[item.item_id] = item
            return item

    def get_equipment(self, item_id: str) -> Optional[EquipmentItem]:
        with self._lock:
            return self.equipment.get(item_id)

    def list_equipment(self) -> List[EquipmentItem]:
        with self._lock:
            return list(self.equipment.values())

    def find_college_buffer_item(self, eq_type: EquipmentType) -> Optional[EquipmentItem]:
        """Find an unassigned, usable item in college inventory to replace a damaged component."""
        with self._lock:
            for item in self.equipment.values():
                if (item.equipment_type == eq_type and 
                    item.kit_id is None and 
                    item.availability == ItemAvailability.USABLE and
                    item.condition == ItemCondition.GOOD):
                    return item
            return None

    # --- Reservation Operations ---
    def save_reservation(self, reservation: Reservation) -> Reservation:
        with self._lock:
            self.reservations[reservation.reservation_id] = reservation
            return reservation

    def get_reservation(self, reservation_id: str) -> Optional[Reservation]:
        with self._lock:
            return self.reservations.get(reservation_id)

    def list_reservations(self) -> List[Reservation]:
        with self._lock:
            return list(self.reservations.values())

    # --- Maintenance Block Operations ---
    def save_maintenance_block(self, block: MaintenanceBlock) -> MaintenanceBlock:
        with self._lock:
            self.maintenance_blocks[block.block_id] = block
            return block

    def get_maintenance_block(self, block_id: str) -> Optional[MaintenanceBlock]:
        with self._lock:
            return self.maintenance_blocks.get(block_id)

    def list_maintenance_blocks(self, kit_id: Optional[str] = None) -> List[MaintenanceBlock]:
        with self._lock:
            blocks = list(self.maintenance_blocks.values())
            if kit_id:
                blocks = [b for b in blocks if b.kit_id == kit_id]
            return blocks

    # --- Booking Restriction Operations ---
    def save_booking_restriction(self, restriction: BookingRestriction) -> BookingRestriction:
        with self._lock:
            self.booking_restrictions[restriction.restriction_id] = restriction
            return restriction

    def list_booking_restrictions(self, club_id: Optional[str] = None) -> List[BookingRestriction]:
        with self._lock:
            restrictions = list(self.booking_restrictions.values())
            if club_id:
                restrictions = [r for r in restrictions if r.club_id == club_id or r.student_id == club_id]
            return restrictions

    # --- Incident Operations ---
    def save_incident(self, incident: Incident) -> Incident:
        with self._lock:
            self.incidents[incident.incident_id] = incident
            return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            return self.incidents.get(incident_id)

    def list_incidents(self) -> List[Incident]:
        with self._lock:
            return list(self.incidents.values())

    # --- Invoice Operations ---
    def save_invoice(self, invoice: PenaltyInvoice) -> PenaltyInvoice:
        with self._lock:
            self.invoices[invoice.invoice_id] = invoice
            return invoice

    def get_invoice(self, invoice_id: str) -> Optional[PenaltyInvoice]:
        with self._lock:
            return self.invoices.get(invoice_id)

    def get_invoices_by_club(self, club_id: str) -> List[PenaltyInvoice]:
        with self._lock:
            return [inv for inv in self.invoices.values() if inv.club_id == club_id or inv.student_id == club_id]

    def list_invoices(self) -> List[PenaltyInvoice]:
        with self._lock:
            return list(self.invoices.values())

    # --- Payment Operations ---
    def save_payment(self, payment: PaymentTransaction) -> PaymentTransaction:
        with self._lock:
            self.payments[payment.transaction_id] = payment
            return payment

    def list_payments(self) -> List[PaymentTransaction]:
        with self._lock:
            return list(self.payments.values())

    # --- Replacement Logs ---
    def add_replacement_log(self, log: ReplacementLog) -> None:
        with self._lock:
            self.replacement_logs.append(log)

    def list_replacement_logs(self) -> List[ReplacementLog]:
        with self._lock:
            return list(self.replacement_logs)
