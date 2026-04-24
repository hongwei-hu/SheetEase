"""Data models for practice suggestions."""

from dataclasses import dataclass

from .rules.metadata import RuleMetadata


@dataclass(frozen=True)
class PracticeSuggestion:
    rule: RuleMetadata
    sheet_name: str
    field_name: str
    current_type: str
    suggested_config: str
    reason: str
