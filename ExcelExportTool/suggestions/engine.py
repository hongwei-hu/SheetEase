"""Suggestion engine for orchestrating rule evaluation."""

from typing import Iterable

from .collectors import NumericSuggestionCollector
from .models import PracticeSuggestion
from .rules.base import SuggestionRule
from .rules.numeric_type_suggestion_rule import NumericTypeSuggestionRule
from .rules.probability_float_constraint_rule import ProbabilityFloatConstraintRule


class SuggestionEngine:
    def __init__(self, rules: Iterable[SuggestionRule] | None = None) -> None:
        self._rules = list(rules) if rules is not None else [
            NumericTypeSuggestionRule(),
            ProbabilityFloatConstraintRule(),
            # ListUniqueConstraintRule 已移除：list 的唯一性检查现由 unilist 类型直接实现
        ]

    def run(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        result: list[PracticeSuggestion] = []
        for rule in self._rules:
            result.extend(rule.evaluate(sheet_name, collector))
        return result
