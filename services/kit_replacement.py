from typing import Optional
from domain.models import (
    EventKit, EquipmentItem, EquipmentType, 
    ItemCondition, ItemAvailability, ReplacementLog
)
from repository.memory_repo import MemoryRepository

class KitReplacementService:
    """
    Handles immediate college equipment replacement.
    When a club damages or loses an item, the college replaces it from buffer stock
    so the primary kit remains 100% complete and available for upcoming reservations.
    """
    def __init__(self, repo: MemoryRepository):
        self.repo = repo

    def replace_damaged_component(
        self, 
        kit_id: str, 
        damaged_item_id: str, 
        organizer_notes: str = "Replaced immediately from college buffer inventory"
    ) -> tuple[bool, Optional[EquipmentItem], str]:
        """
        Executes an atomic replacement of a damaged/missing item in the shared kit.
        Returns (success: bool, replacement_item: Optional[EquipmentItem], message: str)
        """
        kit = self.repo.get_kit(kit_id)
        if not kit:
            return False, None, f"EventKit {kit_id} not found"

        damaged_item = self.repo.get_equipment(damaged_item_id)
        if not damaged_item:
            return False, None, f"Damaged item {damaged_item_id} not found"

        eq_type = damaged_item.equipment_type

        # 1. Look for a usable buffer item in college stock
        buffer_item = self.repo.find_college_buffer_item(eq_type)
        if not buffer_item:
            # No replacement available in campus pool
            kit.is_complete_and_usable = False
            self.repo.save_kit(kit)
            return False, None, f"No backup {eq_type.value} available in college inventory. Kit marked incomplete."

        # 2. Unlink damaged item from kit and mark under repair
        damaged_item.kit_id = None
        damaged_item.availability = ItemAvailability.UNDER_REPAIR if damaged_item.condition == ItemCondition.DAMAGED else ItemAvailability.LOST
        self.repo.save_equipment(damaged_item)

        # 3. Assign the college backup item to the kit
        buffer_item.kit_id = kit.kit_id
        buffer_item.availability = ItemAvailability.USABLE
        buffer_item.condition = ItemCondition.GOOD
        self.repo.save_equipment(buffer_item)

        # 4. Update the event kit item map
        kit.assigned_items[eq_type] = buffer_item.item_id
        kit.is_complete_and_usable = True
        self.repo.save_kit(kit)

        # 5. Log the replacement for auditability
        log = ReplacementLog(
            kit_id=kit.kit_id,
            damaged_item_id=damaged_item.item_id,
            replacement_item_id=buffer_item.item_id,
            equipment_type=eq_type,
            organizer_notes=organizer_notes
        )
        self.repo.add_replacement_log(log)
        
        return True, buffer_item, f"College replaced {eq_type.value} with spare item {buffer_item.serial_number}. Kit is complete and usable."
