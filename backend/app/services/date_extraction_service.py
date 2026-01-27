"""
Service for extracting dates from filenames.

Supports multiple date formats with confidence scoring:
- ISO format: 2025-01-20-notes.md (confidence: 1.0)
- ISO underscore: 2025_01_20_meeting.md (confidence: 1.0)
- Compact: meeting_20250120.md (confidence: 0.9)
- Verbose month: January 15 notes.md (confidence: 0.8)
"""

import re
from datetime import date
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Month name mappings
MONTH_NAMES = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12
}


@dataclass
class ExtractedDate:
    """Result of date extraction from a filename."""
    date: date
    source: str  # 'filename', 'content', or 'created_at'
    confidence: float  # 0.0 to 1.0


class DateExtractionService:
    """Extracts dates from filenames using various patterns."""

    # Regex patterns ordered by specificity/confidence
    PATTERNS = [
        # ISO format: 2025-01-20 at the start
        (r'^(\d{4})-(\d{2})-(\d{2})[-_\s]', 'iso_start', 1.0),
        # ISO format with underscores: 2025_01_20 at the start
        (r'^(\d{4})_(\d{2})_(\d{2})[-_\s]', 'iso_underscore_start', 1.0),
        # ISO format anywhere in filename
        (r'(\d{4})-(\d{2})-(\d{2})', 'iso_anywhere', 0.95),
        # ISO format with underscores anywhere
        (r'(\d{4})_(\d{2})_(\d{2})', 'iso_underscore_anywhere', 0.95),
        # Compact format: 20250120 (8 digits that look like YYYYMMDD)
        (r'(?:^|[_\-\s])(\d{4})(\d{2})(\d{2})(?:[_\-\s.]|$)', 'compact', 0.9),
    ]

    # Pattern for verbose month names: "January 15 notes.md" or "January 15, 2024.md"
    VERBOSE_PATTERN = re.compile(
        r'(?:^|[\s_\-])(' + '|'.join(MONTH_NAMES.keys()) + r')\s*(\d{1,2})(?:\s*,?\s*(\d{4}))?(?:[\s_\-.]|$)',
        re.IGNORECASE
    )

    # Pattern for "Month Dayth, Year" format: "January 2nd, 2025.md", "March 27th, 2024.md"
    ORDINAL_DATE_PATTERN = re.compile(
        r'^(' + '|'.join(MONTH_NAMES.keys()) + r')\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})',
        re.IGNORECASE
    )

    def extract_date_from_filename(self, filename: str) -> Optional[ExtractedDate]:
        """
        Extract a date from a filename.

        Args:
            filename: The filename to extract a date from

        Returns:
            ExtractedDate if a date was found, None otherwise
        """
        if not filename:
            return None

        # Remove file extension for cleaner matching
        name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename

        # Try each pattern in order of confidence
        for pattern, pattern_name, confidence in self.PATTERNS:
            match = re.search(pattern, name_without_ext)
            if match:
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))

                    # Validate the date
                    extracted = date(year, month, day)

                    # Sanity check: date should be reasonable (not too far in past or future)
                    today = date.today()
                    if extracted.year < 1990 or extracted > today.replace(year=today.year + 2):
                        logger.debug(f"Date {extracted} from {filename} failed sanity check")
                        continue

                    logger.debug(f"Extracted date {extracted} from {filename} using pattern {pattern_name}")
                    return ExtractedDate(
                        date=extracted,
                        source='filename',
                        confidence=confidence
                    )
                except ValueError:
                    # Invalid date (e.g., month=13 or day=32)
                    continue

        # Try ordinal date pattern first (more specific): "January 2nd, 2025.md"
        match = self.ORDINAL_DATE_PATTERN.search(name_without_ext)
        if match:
            try:
                month_str = match.group(1).lower()
                day = int(match.group(2))
                year = int(match.group(3))

                month = MONTH_NAMES.get(month_str)
                if month is None:
                    return None

                extracted = date(year, month, day)

                # Sanity check
                today = date.today()
                if extracted.year < 1990 or extracted > today.replace(year=today.year + 2):
                    logger.debug(f"Date {extracted} from {filename} failed sanity check")
                else:
                    logger.debug(f"Extracted date {extracted} from {filename} using ordinal pattern")
                    return ExtractedDate(
                        date=extracted,
                        source='filename',
                        confidence=0.95
                    )
            except ValueError:
                pass

        # Try verbose month pattern: "January 15 notes.md"
        match = self.VERBOSE_PATTERN.search(name_without_ext)
        if match:
            try:
                month_str = match.group(1).lower()
                day = int(match.group(2))
                year_str = match.group(3)

                month = MONTH_NAMES.get(month_str)
                if month is None:
                    return None

                # If no year specified, use current year (or previous year if month is in future)
                if year_str:
                    year = int(year_str)
                else:
                    today = date.today()
                    year = today.year
                    # If the month would be in the future, assume last year
                    if month > today.month or (month == today.month and day > today.day):
                        year -= 1

                extracted = date(year, month, day)

                logger.debug(f"Extracted date {extracted} from {filename} using verbose pattern")
                return ExtractedDate(
                    date=extracted,
                    source='filename',
                    confidence=0.8
                )
            except ValueError:
                pass

        return None

    def extract_date_with_fallback(
        self,
        filename: str,
        created_at: Optional[date] = None
    ) -> Optional[ExtractedDate]:
        """
        Extract date from filename, falling back to created_at if no date found.

        Args:
            filename: The filename to extract a date from
            created_at: Optional fallback date (e.g., file creation time)

        Returns:
            ExtractedDate if any date was found, None otherwise
        """
        # Try filename first
        result = self.extract_date_from_filename(filename)
        if result:
            return result

        # Fall back to created_at
        if created_at:
            return ExtractedDate(
                date=created_at,
                source='created_at',
                confidence=0.5
            )

        return None
