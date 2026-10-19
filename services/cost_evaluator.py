from domain.models import EquipmentType, ItemCondition
from domain.rate_card import EquipmentRateCard

class CostEvaluationService:
    """Calculates repair/replacement fees and administrative surcharges for equipment damage."""
    
    def evaluate_cost(
        self, 
        equipment_type: EquipmentType, 
        condition: ItemCondition
    ) -> dict:
        base_cost, handling_fee, total_amount_due = EquipmentRateCard.calculate_assessment(
            equipment_type=equipment_type,
            condition=condition
        )
        return {
            "equipment_type": equipment_type.value,
            "condition": condition.value,
            "base_cost": base_cost,
            "handling_fee": handling_fee,
            "total_amount_due": total_amount_due
        }
