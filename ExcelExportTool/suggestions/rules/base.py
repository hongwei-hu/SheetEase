"""Rule protocol for practice suggestions."""

from typing import Protocol

from ..collectors import NumericSuggestionCollector
from ..models import PracticeSuggestion
from .metadata import RuleMetadata


class SuggestionRule(Protocol):
    @property
    def metadata(self) -> RuleMetadata:
        ...

    def evaluate(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        ...
