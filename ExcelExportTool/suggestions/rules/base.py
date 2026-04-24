"""Rule protocol for practice suggestions."""

from typing import Iterable, Protocol

from ..collectors import NumericFieldStats
from ..models import PracticeSuggestion


class SuggestionRule(Protocol):
    def evaluate(self, sheet_name: str, stats: Iterable[NumericFieldStats]) -> list[PracticeSuggestion]:
        ...
