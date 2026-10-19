from typing import Dict
from domain.models import EquipmentType, ItemCondition

class EquipmentRateCard:
    """
    Standardized rate card in Indian Rupees (INR / ₹) 
    for college equipment repairs, replacement valuations, and administrative triage fees.
    """
    
    # Base repair quotes in Indian Rupees (₹)
    REPAIR_RATES: Dict[EquipmentType, float] = {
        EquipmentType.CAMERA: 2500.00,      # Optical unit calibration, sensor clean, port fix (₹2,500)
        EquipmentType.MICROPHONE: 700.00,   # Capsule dent fix, wireless diaphragm repair (₹700)
        EquipmentType.TRIPOD: 450.00        # Leg clamp lock replacement, fluid head tightening (₹450)
    }
    
    # Full unit replacement values in Indian Rupees (₹)
    REPLACEMENT_VALUES: Dict[EquipmentType, float] = {
        EquipmentType.CAMERA: 38000.00,     # Full 4K campus cinema camera body + lens (₹38,000)
        EquipmentType.MICROPHONE: 6500.00,  # Studio dual-channel wireless mic kit (₹6,500)
        EquipmentType.TRIPOD: 3200.00       # Heavy-duty carbon-fiber video tripod (₹3,200)
    }
    
    # Administrative triage fee percentage
    ADMIN_HANDLING_PERCENTAGE: float = 0.15  # 15% handling fee
    MIN_ADMIN_HANDLING_FEE: float = 100.00   # ₹100 minimum surcharge

    @classmethod
    def calculate_assessment(
        cls, 
        equipment_type: EquipmentType, 
        condition: ItemCondition
    ) -> tuple[float, float, float]:
        """
        Calculates (base_cost, handling_fee, total_amount_due) in INR (₹).
        - If MISSING: full replacement valuation is billed.
        - If DAMAGED: approved repair quote is billed.
        """
        if condition == ItemCondition.MISSING:
            base_cost = cls.REPLACEMENT_VALUES.get(equipment_type, 3000.00)
        else:
            base_cost = cls.REPAIR_RATES.get(equipment_type, 700.00)
            
        handling_fee = max(base_cost * cls.ADMIN_HANDLING_PERCENTAGE, cls.MIN_ADMIN_HANDLING_FEE)
        total_due = round(base_cost + handling_fee, 2)
        return round(base_cost, 2), round(handling_fee, 2), total_due
