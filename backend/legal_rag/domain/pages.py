"""Validate explicit page lists and ranges against cited page metadata."""

from __future__ import annotations

import re

_RANGE_SEPARATOR = r"(?:[-\u2013\u2014]|\bto\b)"
_ITEM = rf"\d+(?:\s*{_RANGE_SEPARATOR}\s*\d+)?"
_PAGE_REFERENCES = re.compile(
    rf"\bpages?\s*[:#]?\s*(?P<items>{_ITEM}"
    rf"(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*){_ITEM})*)",
    re.IGNORECASE,
)
_PAGE_ITEM = re.compile(rf"(?P<start>\d+)(?:\s*{_RANGE_SEPARATOR}\s*(?P<end>\d+))?", re.IGNORECASE)


def page_references_supported(text: str, supported_pages: set[str]) -> bool:
    """Require all listed pages, including range interiors, without expanding ranges."""
    for reference in _PAGE_REFERENCES.finditer(text):
        for item in _PAGE_ITEM.finditer(reference.group("items")):
            start, end = item.group("start"), item.group("end")
            if start not in supported_pages or (end is not None and end not in supported_pages):
                return False
            if end is None:
                continue
            try:
                lower, upper = int(start), int(end)
                numeric_pages = {int(page) for page in supported_pages if page.isdecimal()}
                pages_in_range = sum(lower <= page <= upper for page in numeric_pages)
            except ValueError:
                return False
            if upper < lower or pages_in_range != upper - lower + 1:
                return False
    return True
