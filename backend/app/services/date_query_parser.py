"""
Service for parsing temporal queries from user input.

Detects date-related phrases in queries and converts them to date ranges:
- "in January" -> Jan 1-31 of the most recent January
- "last week" -> 7 days ago to today
- "December 2024" -> Dec 1-31, 2024
- "yesterday" -> yesterday's date
"""

import re
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional, Tuple
from calendar import monthrange
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

# Reverse mapping for display
MONTH_DISPLAY_NAMES = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}


@dataclass
class DateRange:
    """A date range with start and end dates."""
    start: date
    end: date

    def __str__(self) -> str:
        if self.start == self.end:
            return self.start.strftime('%Y-%m-%d')
        return f"{self.start.strftime('%Y-%m-%d')} to {self.end.strftime('%Y-%m-%d')}"


@dataclass
class ParsedQuery:
    """Result of parsing a query for temporal intent."""
    clean_query: str  # Query with temporal phrases removed for semantic search
    date_range: Optional[DateRange]
    has_temporal_intent: bool
    temporal_description: Optional[str] = None  # Human-readable description of the date range


class DateQueryParser:
    """Parses user queries for temporal intent and extracts date ranges."""

    # Patterns for relative time expressions
    RELATIVE_PATTERNS = [
        # "yesterday"
        (r'\byesterday\b', '_parse_yesterday'),
        # "today"
        (r'\btoday\b', '_parse_today'),
        # "last week"
        (r'\blast\s+week\b', '_parse_last_week'),
        # "this week"
        (r'\bthis\s+week\b', '_parse_this_week'),
        # "last month"
        (r'\blast\s+month\b', '_parse_last_month'),
        # "this month"
        (r'\bthis\s+month\b', '_parse_this_month'),
        # "last N days"
        (r'\blast\s+(\d+)\s+days?\b', '_parse_last_n_days'),
        # "N days ago"
        (r'(\d+)\s+days?\s+ago\b', '_parse_n_days_ago'),
    ]

    # Pattern for month with optional year: "in January", "January 2024", "in Jan 2024", "in February of 2021"
    MONTH_PATTERN = re.compile(
        r'(?:in\s+)?(' + '|'.join(MONTH_NAMES.keys()) + r')(?:\s+(?:of\s+)?(\d{4})|\s+of\s+(\d{4}))?\b',
        re.IGNORECASE
    )

    # Pattern for specific date: "on January 15", "January 15, 2024", "February 8 in 2021"
    SPECIFIC_DATE_PATTERN = re.compile(
        r'(?:on\s+)?(' + '|'.join(MONTH_NAMES.keys()) + r')\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4})|\s+(?:in|of)\s+(\d{4}))?\b',
        re.IGNORECASE
    )

    # Pattern for ISO dates: "2024-01-15", "on 2024-01-15"
    ISO_DATE_PATTERN = re.compile(
        r'(?:on\s+)?(\d{4})-(\d{2})-(\d{2})\b'
    )

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Parse a query for temporal intent.

        Args:
            query: The user's query string

        Returns:
            ParsedQuery with date range if temporal intent was detected
        """
        if not query:
            return ParsedQuery(
                clean_query=query,
                date_range=None,
                has_temporal_intent=False
            )

        # Try each pattern type
        result = self._try_relative_patterns(query)
        if result:
            return result

        result = self._try_specific_date_pattern(query)
        if result:
            return result

        result = self._try_iso_date_pattern(query)
        if result:
            return result

        result = self._try_month_pattern(query)
        if result:
            return result

        # No temporal intent detected
        return ParsedQuery(
            clean_query=query,
            date_range=None,
            has_temporal_intent=False
        )

    def _try_relative_patterns(self, query: str) -> Optional[ParsedQuery]:
        """Try to match relative time patterns."""
        for pattern, method_name in self.RELATIVE_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                method = getattr(self, method_name)
                date_range, description = method(match)
                clean_query = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
                clean_query = re.sub(r'\s+', ' ', clean_query)  # Normalize whitespace

                return ParsedQuery(
                    clean_query=clean_query or query,  # Keep original if nothing left
                    date_range=date_range,
                    has_temporal_intent=True,
                    temporal_description=description
                )
        return None

    def _try_month_pattern(self, query: str) -> Optional[ParsedQuery]:
        """Try to match month patterns like 'in January', 'January 2024', or 'in February of 2021'."""
        match = self.MONTH_PATTERN.search(query)
        if match:
            month_str = match.group(1).lower()
            # Year can be in group 2 (e.g., "January 2024") or group 3 (e.g., "January of 2024")
            year_str = match.group(2) or match.group(3)

            month = MONTH_NAMES.get(month_str)
            if month is None:
                return None

            today = date.today()

            if year_str:
                year = int(year_str)
            else:
                # Use the most recent occurrence of this month
                year = today.year
                # If the month is in the future this year, use last year
                if month > today.month:
                    year -= 1

            # Get the last day of the month
            _, last_day = monthrange(year, month)

            date_range = DateRange(
                start=date(year, month, 1),
                end=date(year, month, last_day)
            )

            month_name = MONTH_DISPLAY_NAMES[month]
            description = f"{month_name} {year}"

            # Remove the matched text from the query
            clean_query = query[:match.start()] + query[match.end():]
            clean_query = re.sub(r'\s+', ' ', clean_query).strip()

            return ParsedQuery(
                clean_query=clean_query or query,
                date_range=date_range,
                has_temporal_intent=True,
                temporal_description=description
            )
        return None

    def _try_specific_date_pattern(self, query: str) -> Optional[ParsedQuery]:
        """Try to match specific date patterns like 'January 15', 'on January 15, 2024', or 'February 8 in 2021'."""
        match = self.SPECIFIC_DATE_PATTERN.search(query)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            # Year can be in group 3 (e.g., "January 15, 2024") or group 4 (e.g., "February 8 in 2021")
            year_str = match.group(3) or match.group(4)

            month = MONTH_NAMES.get(month_str)
            if month is None:
                return None

            today = date.today()

            if year_str:
                year = int(year_str)
            else:
                # Use the most recent occurrence
                year = today.year
                try:
                    candidate = date(year, month, day)
                    if candidate > today:
                        year -= 1
                except ValueError:
                    return None

            try:
                specific_date = date(year, month, day)
            except ValueError:
                return None

            date_range = DateRange(start=specific_date, end=specific_date)

            month_name = MONTH_DISPLAY_NAMES[month]
            description = f"{month_name} {day}, {year}"

            clean_query = query[:match.start()] + query[match.end():]
            clean_query = re.sub(r'\s+', ' ', clean_query).strip()

            return ParsedQuery(
                clean_query=clean_query or query,
                date_range=date_range,
                has_temporal_intent=True,
                temporal_description=description
            )
        return None

    def _try_iso_date_pattern(self, query: str) -> Optional[ParsedQuery]:
        """Try to match ISO date patterns like '2024-01-15'."""
        match = self.ISO_DATE_PATTERN.search(query)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                specific_date = date(year, month, day)
            except ValueError:
                return None

            date_range = DateRange(start=specific_date, end=specific_date)
            description = specific_date.strftime('%B %d, %Y')

            clean_query = query[:match.start()] + query[match.end():]
            clean_query = re.sub(r'\s+', ' ', clean_query).strip()

            return ParsedQuery(
                clean_query=clean_query or query,
                date_range=date_range,
                has_temporal_intent=True,
                temporal_description=description
            )
        return None

    # Methods for relative patterns

    def _parse_yesterday(self, match: re.Match) -> Tuple[DateRange, str]:
        yesterday = date.today() - timedelta(days=1)
        return DateRange(start=yesterday, end=yesterday), "yesterday"

    def _parse_today(self, match: re.Match) -> Tuple[DateRange, str]:
        today = date.today()
        return DateRange(start=today, end=today), "today"

    def _parse_last_week(self, match: re.Match) -> Tuple[DateRange, str]:
        today = date.today()
        start = today - timedelta(days=7)
        return DateRange(start=start, end=today), "last 7 days"

    def _parse_this_week(self, match: re.Match) -> Tuple[DateRange, str]:
        today = date.today()
        # Start of week (Monday)
        start = today - timedelta(days=today.weekday())
        return DateRange(start=start, end=today), "this week"

    def _parse_last_month(self, match: re.Match) -> Tuple[DateRange, str]:
        today = date.today()
        # First day of last month
        if today.month == 1:
            start = date(today.year - 1, 12, 1)
            _, last_day = monthrange(today.year - 1, 12)
            end = date(today.year - 1, 12, last_day)
        else:
            start = date(today.year, today.month - 1, 1)
            _, last_day = monthrange(today.year, today.month - 1)
            end = date(today.year, today.month - 1, last_day)

        month_name = MONTH_DISPLAY_NAMES[start.month]
        return DateRange(start=start, end=end), f"last month ({month_name})"

    def _parse_this_month(self, match: re.Match) -> Tuple[DateRange, str]:
        today = date.today()
        start = date(today.year, today.month, 1)
        month_name = MONTH_DISPLAY_NAMES[today.month]
        return DateRange(start=start, end=today), f"this month ({month_name})"

    def _parse_last_n_days(self, match: re.Match) -> Tuple[DateRange, str]:
        n = int(match.group(1))
        today = date.today()
        start = today - timedelta(days=n)
        return DateRange(start=start, end=today), f"last {n} days"

    def _parse_n_days_ago(self, match: re.Match) -> Tuple[DateRange, str]:
        n = int(match.group(1))
        target_date = date.today() - timedelta(days=n)
        return DateRange(start=target_date, end=target_date), f"{n} days ago"
