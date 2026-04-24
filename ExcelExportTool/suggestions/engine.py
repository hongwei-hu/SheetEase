"""Suggestion engine for orchestrating rule evaluation."""

from typing import Iterable

from .collectors import NumericSuggestionCollector
from .models import PracticeSuggestion
from .rules.base import SuggestionRule
from .rules.numeric_type_suggestion_rule import NumericTypeSuggestionRule


class SuggestionEngine:
    def __init__(self, rules: Iterable[SuggestionRule] | None = None) -> None:
        self._rules = list(rules) if rules is not None else [NumericTypeSuggestionRule()]

    def run(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        stats = list(collector.get_numeric_stats())
        result: list[PracticeSuggestion] = []
        for rule in self._rules:
            result.extend(rule.evaluate(sheet_name, stats))
        return result
