"""Data models for practice suggestions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PracticeSuggestion:
    sheet_name: str
    field_name: str
    current_type: str
    suggested_type: str
    reason: str
