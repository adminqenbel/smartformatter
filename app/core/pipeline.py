"""
Processing Pipeline Orchestrator.
Coordinates CV detection, orientation, quality validation, pair synchronization,
FormatProfile management, and export execution.
"""
from typing import Optional, List, Union
from pathlib import Path

from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE, ProfileRegistry
from app.core.models import (
    ProcessingMode,
    CardPair,
    CardEntry,
    SheetQueue,
    ProcessedImage,
    CornerPoints,
    EnhancementMode,
)
from app.processing.card_processor import CardProcessor
from app.processing.sheet_processor import SheetProcessor
from app.utils.logger import get_logger

logger = get_logger("pipeline")


class FormatterPipeline:
    """Central processing engine orchestrating Card and Sheet workflows."""

    def __init__(self):
        self.mode = ProcessingMode.CARD
        self.active_card_profile: FormatProfile = CARD_PROFILE
        self.card_processor = CardProcessor()
        self.sheet_processor = SheetProcessor()

        self.card_entry = CardEntry(format_profile=self.active_card_profile)
        self.card_pair = CardPair(format_profile=self.active_card_profile)
        self.sheet_queue = SheetQueue()
        self.active_enhancement = EnhancementMode.ORIGINAL

    def set_mode(self, mode: ProcessingMode):
        """Switches active processing mode."""
        self.mode = mode
        logger.info(f"Switched mode to {mode.value}")

    # ================= SIMPLIFIED CARD ENTRY (one entry) =================

    def set_card_images(
        self,
        front_source=None,
        back_source=None,
        profile: Optional[FormatProfile] = None,
    ) -> Optional[tuple]:
        """
        Processes the front and back photographs as ONE card entry.
        Returns (front_processed, back_processed). Either may be None.
        """
        active_profile = profile or self.active_card_profile
        front_proc = None
        back_proc = None
        if front_source is not None:
            front_proc = self.card_processor.process_image(
                front_source, profile=active_profile,
                enhancement_mode=self.active_enhancement,
            )
        if back_source is not None:
            back_proc = self.card_processor.process_image(
                back_source, profile=active_profile,
                enhancement_mode=self.active_enhancement,
            )

        self.card_entry.front = front_proc
        self.card_entry.back = back_proc
        self.card_entry.format_profile = active_profile
        self.active_card_profile = active_profile

        self.card_pair.front = front_proc
        self.card_pair.back = back_proc
        self.card_pair.format_profile = active_profile
        self.card_processor.synchronize_pair(self.card_pair)
        return front_proc, back_proc

    def set_card_profile(self, profile_or_id: Union[str, FormatProfile]):
        """Sets the active physical format profile for Card Mode (e.g. 'card' or 'long_form')."""
        if isinstance(profile_or_id, str):
            profile = ProfileRegistry.get_profile(profile_or_id)
        else:
            profile = profile_or_id

        self.active_card_profile = profile
        self.card_pair.format_profile = profile
        self.card_entry.format_profile = profile
        if self.card_entry.front is not None:
            self.card_entry.front.format_profile = profile
        if self.card_entry.back is not None:
            self.card_entry.back.format_profile = profile

        if self.card_pair.front is not None:
            self.card_processor.update_profile(self.card_pair.front, profile)
        if self.card_pair.back is not None:
            self.card_processor.update_profile(self.card_pair.back, profile)

        self.card_processor.synchronize_pair(self.card_pair)
        logger.info(f"Active Card Mode profile updated to: {profile.name} ({profile.dimensions_mm_str})")

    def set_card_front(self, source: Union[str, Path]) -> Optional[ProcessedImage]:
        """Loads and processes the front card image using the active profile."""
        logger.info(f"Loading Card Front with profile {self.active_card_profile.name}: {source}")
        processed = self.card_processor.process_image(
            source,
            profile=self.active_card_profile,
            enhancement_mode=self.active_enhancement
        )
        self.card_pair.front = processed
        self.card_pair.format_profile = self.active_card_profile
        self.card_entry.front = processed
        self.card_entry.format_profile = self.active_card_profile
        self.card_processor.synchronize_pair(self.card_pair)
        return processed

    def set_card_back(self, source: Union[str, Path]) -> Optional[ProcessedImage]:
        """Loads and processes the back card image using the active profile."""
        logger.info(f"Loading Card Back with profile {self.active_card_profile.name}: {source}")
        processed = self.card_processor.process_image(
            source,
            profile=self.active_card_profile,
            enhancement_mode=self.active_enhancement
        )
        self.card_pair.back = processed
        self.card_pair.format_profile = self.active_card_profile
        self.card_entry.back = processed
        self.card_entry.format_profile = self.active_card_profile
        self.card_processor.synchronize_pair(self.card_pair)
        return processed

    def swap_card_sides(self):
        """Swaps FRONT and BACK cards."""
        self.card_pair.swap_sides()
        self.card_entry.front = self.card_pair.front
        self.card_entry.back = self.card_pair.back
        logger.info("Swapped card Front and Back sides.")

    # ================= SHEET MODE METHODS =================

    def add_sheet_pages(self, sources: List[Union[str, Path]]) -> List[ProcessedImage]:
        """Adds and processes multiple sheet pages."""
        added = []
        for src in sources:
            logger.info(f"Adding Sheet Page: {src}")
            page = self.sheet_processor.process_page(
                src, enhancement_mode=self.active_enhancement
            )
            if page is not None:
                self.sheet_queue.add_page(page)
                added.append(page)
        return added

    def remove_sheet_page(self, index: int):
        """Removes a sheet page by index."""
        self.sheet_queue.remove_page(index)

    def move_sheet_page(self, from_idx: int, to_idx: int):
        """Moves page from one position to another."""
        if 0 <= from_idx < len(self.sheet_queue.pages) and 0 <= to_idx < len(self.sheet_queue.pages):
            page = self.sheet_queue.pages.pop(from_idx)
            self.sheet_queue.pages.insert(to_idx, page)

    # ================= COMMON CORRECTION & ENHANCEMENT =================

    def update_item_corners(self, processed: ProcessedImage, new_corners: CornerPoints) -> ProcessedImage:
        """Updates corners and recomputes the image."""
        if self.mode == ProcessingMode.CARD:
            res = self.card_processor.recompute_from_corners(processed, new_corners)
            self.card_processor.synchronize_pair(self.card_pair)
            # Sync to card_entry
            if self.card_entry.front is not None and res is self.card_entry.front:
                self.card_entry.front = res
            if self.card_entry.back is not None and res is self.card_entry.back:
                self.card_entry.back = res
            return res
        else:
            return self.sheet_processor.recompute_from_corners(processed, new_corners)

    def rotate_item(self, processed: ProcessedImage, angle_deg: int) -> ProcessedImage:
        """Applies relative manual rotation (e.g. +90 deg)."""
        new_manual = (processed.manual_rotation_deg + angle_deg) % 360
        return self.set_item_rotation(processed, new_manual)

    def set_item_rotation(self, processed: ProcessedImage, manual_deg: int) -> ProcessedImage:
        """Sets exact manual rotation of the item."""
        if self.mode == ProcessingMode.CARD:
            res = self.card_processor.update_manual_rotation(processed, manual_deg)
            self.card_processor.synchronize_pair(self.card_pair)
            if self.card_entry.front is not None and res is self.card_entry.front:
                self.card_entry.front = res
            if self.card_entry.back is not None and res is self.card_entry.back:
                self.card_entry.back = res
            return res
        else:
            return self.sheet_processor.update_manual_rotation(processed, manual_deg)

    def set_global_enhancement(self, mode: EnhancementMode):
        """Applies enhancement mode to all active items."""
        self.active_enhancement = mode
        if self.mode == ProcessingMode.CARD:
            if self.card_pair.front is not None:
                self.card_pair.front.enhancement_mode = mode
                self.card_processor.recompute_from_corners(self.card_pair.front, self.card_pair.front.current_corners)
            if self.card_pair.back is not None:
                self.card_pair.back.enhancement_mode = mode
                self.card_processor.recompute_from_corners(self.card_pair.back, self.card_pair.back.current_corners)
            self.card_processor.synchronize_pair(self.card_pair)
            # Sync card_entry
            self.card_entry.front = self.card_pair.front
            self.card_entry.back = self.card_pair.back
        else:
            for page in self.sheet_queue.pages:
                page.enhancement_mode = mode
                self.sheet_processor.recompute_from_corners(page, page.current_corners)

    def reset(self):
        """Resets the pipeline state."""
        self.card_pair = CardPair(format_profile=self.active_card_profile)
        self.card_entry = CardEntry(format_profile=self.active_card_profile)
        self.sheet_queue = SheetQueue()
