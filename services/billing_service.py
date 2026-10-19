from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from domain.models import (
    PenaltyInvoice, PaymentTransaction, Club, ClubStanding,
    InvoiceStatus, PaymentStatus, EquipmentType, ItemCondition
)
from domain.rate_card import EquipmentRateCard
from repository.memory_repo import MemoryRepository

class PenaltyBillingService:
    """
    Manages damage liability invoicing, progressive payment tracking,
    and club financial standing (restricting booking if unpaid).
    """
    def __init__(self, repo: MemoryRepository):
        self.repo = repo

    def issue_damage_invoice(
        self,
        incident_id: str,
        club_id: str,
        item_id: str,
        equipment_type: EquipmentType,
        condition: ItemCondition,
        due_days: int = 7
    ) -> PenaltyInvoice:
        """Calculates cost, creates an invoice, and updates club liability balance."""
        club = self.repo.get_club(club_id)
        if not club:
            raise ValueError(f"Club {club_id} not found")

        base_cost, handling_fee, total_due = EquipmentRateCard.calculate_assessment(
            equipment_type=equipment_type,
            condition=condition
        )

        now = datetime.now(timezone.utc)
        due_date = now + timedelta(days=due_days)

        invoice = PenaltyInvoice(
            incident_id=incident_id,
            club_id=club_id,
            item_id=item_id,
            equipment_type=equipment_type,
            base_cost=base_cost,
            handling_fee=handling_fee,
            total_amount_due=total_due,
            issued_at=now,
            due_date=due_date,
            status=InvoiceStatus.ISSUED
        )
        self.repo.save_invoice(invoice)

        # Update club balance and set status to DEBARRED (immediate booking block upon penalty)
        club.outstanding_balance = round(club.outstanding_balance + total_due, 2)
        club.financial_standing = ClubStanding.DEBARRED
        self.repo.save_club(club)

        return invoice

    def mark_club_debarred(self, club_id: str) -> Club:
        """Explicitly debars a club from booking due to unpaid penalties."""
        club = self.repo.get_club(club_id)
        if not club:
            raise ValueError(f"Club {club_id} not found")
        club.financial_standing = ClubStanding.DEBARRED
        return self.repo.save_club(club)

    def lift_club_debarment(self, club_id: str) -> Club:
        """Lifts debarment and restores student good standing if they have no unpaid balance."""
        club = self.repo.get_club(club_id)
        if not club:
            raise ValueError(f"Club {club_id} not found")
        if club.outstanding_balance > 0:
            raise ValueError(f"Cannot lift debarment: student has outstanding balance of ₹{club.outstanding_balance:,.2f}")
        club.financial_standing = ClubStanding.GOOD_STANDING
        return self.repo.save_club(club)

    def trigger_overdue_check(self) -> List[PenaltyInvoice]:
        """Scans for invoices past due date and transitions unpaid clubs to DEBARRED."""
        now = datetime.now(timezone.utc)
        overdue_invoices = []
        for inv in self.repo.list_invoices():
            due = inv.due_date if inv.due_date.tzinfo else inv.due_date.replace(tzinfo=timezone.utc)
            if inv.status == InvoiceStatus.ISSUED and due < now:
                inv.status = InvoiceStatus.OVERDUE
                self.repo.save_invoice(inv)
                overdue_invoices.append(inv)
                
                club = self.repo.get_club(inv.club_id)
                if club:
                    club.financial_standing = ClubStanding.DEBARRED
                    self.repo.save_club(club)
        return overdue_invoices

    def process_payment(
        self,
        invoice_id: str,
        amount: Optional[float] = None
    ) -> Tuple[bool, Optional[PaymentTransaction], str]:
        """
        Settles a damage invoice.
        When paid in full, updates club balance and clears debarment restrictions.
        """
        invoice = self.repo.get_invoice(invoice_id)
        if not invoice:
            return False, None, f"Invoice {invoice_id} not found"

        if invoice.status == InvoiceStatus.PAID:
            return False, None, "Invoice is already paid in full"

        club = self.repo.get_club(invoice.club_id)
        if not club:
            return False, None, f"Club {invoice.club_id} not found"

        if amount is not None:
            if amount <= 0:
                return False, None, "Payment amount must be greater than ₹0.00"
            if round(amount, 2) > round(invoice.total_amount_due, 2):
                return False, None, f"Payment amount (₹{amount:,.2f}) cannot exceed invoice amount due (₹{invoice.total_amount_due:,.2f})"

        pay_amount = amount if amount is not None else invoice.total_amount_due

        # Record payment transaction
        txn = PaymentTransaction(
            invoice_id=invoice.invoice_id,
            club_id=club.club_id,
            amount_paid=pay_amount,
            status=PaymentStatus.SUCCESS
        )
        self.repo.save_payment(txn)

        # Update invoice status
        if round(pay_amount, 2) >= round(invoice.total_amount_due, 2):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = txn.paid_at
            invoice.transaction_ref = txn.reference_id
        else:
            invoice.total_amount_due = round(invoice.total_amount_due - pay_amount, 2)
        self.repo.save_invoice(invoice)

        # Deduct balance from club ledger
        club.outstanding_balance = max(0.0, round(club.outstanding_balance - pay_amount, 2))

        # Check if club has any other unpaid overdue invoices
        unpaid_invoices = [
            inv for inv in self.repo.get_invoices_by_club(club.club_id)
            if inv.status in (InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE)
        ]

        if not unpaid_invoices and club.outstanding_balance == 0.0:
            club.financial_standing = ClubStanding.GOOD_STANDING
            msg = f"Payment of ₹{pay_amount:,.2f} successful. All dues cleared. Booking privileges RESTORED."
        else:
            msg = f"Payment of ₹{pay_amount:,.2f} recorded. Remaining balance: ₹{club.outstanding_balance:,.2f}."

        self.repo.save_club(club)
        return True, txn, msg

    def get_payment_related_data(self, club_id: str) -> dict:
        """Compiles complete payment and billing data for a team."""
        club = self.repo.get_club(club_id)
        if not club:
            raise ValueError(f"Club {club_id} not found")

        invoices = self.repo.get_invoices_by_club(club_id)
        all_payments = [p for p in self.repo.list_payments() if p.club_id == club_id]

        return {
            "club_id": club.club_id,
            "club_name": club.name,
            "financial_standing": club.financial_standing.value,
            "is_booking_restricted": club.financial_standing == ClubStanding.DEBARRED,
            "outstanding_balance": club.outstanding_balance,
            "invoices": [
                {
                    "invoice_id": inv.invoice_id,
                    "equipment_type": inv.equipment_type.value,
                    "base_cost": inv.base_cost,
                    "handling_fee": inv.handling_fee,
                    "total_amount_due": inv.total_amount_due,
                    "status": inv.status.value,
                    "issued_at": inv.issued_at.isoformat(),
                    "due_date": inv.due_date.isoformat(),
                    "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
                    "transaction_ref": inv.transaction_ref
                }
                for inv in invoices
            ],
            "payments_history": [
                {
                    "transaction_id": p.transaction_id,
                    "invoice_id": p.invoice_id,
                    "amount_paid": p.amount_paid,
                    "reference_id": p.reference_id,
                    "paid_at": p.paid_at.isoformat(),
                    "status": p.status.value
                }
                for p in all_payments
            ]
        }
