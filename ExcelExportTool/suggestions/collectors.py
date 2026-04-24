"""Collectors for practice suggestions."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable

from ..utils.type_utils import parse_type_annotation
from ..validation.constraint_checker import parse_constraint_str, split_type_and_constraint_str


_PLAIN_INT_DECLARED_TYPES = {"int", "int32", "integer"}
_PLAIN_FLOAT_DECLARED_TYPES = {"float", "double"}


@dataclass
class NumericFieldStats:
    field_name: str
    declared_type: str
    type_base: str
    has_nonnegative_constraint: bool
    has_positive_constraint: bool
    sample_count: int = 0
    positive_count: int = 0
    nonnegative_count: int = 0
    zero_count: int = 0


class NumericSuggestionCollector:
    """Collect scalar int/float field value distribution for recommendations."""

    def __init__(self) -> None:
        self._stats: Dict[int, NumericFieldStats] = {}

    def observe(self, col_index: int, field_name: str, type_str: str, value: Any) -> None:
        stats = self._stats.get(col_index)
        if stats is None:
            stats = self._build_stats_if_eligible(field_name, type_str)
            if stats is None:
                return
            self._stats[col_index] = stats

        if isinstance(value, bool):
            return
        if not isinstance(value, (int, float)):
            return

        numeric_value = float(value)
        stats.sample_count += 1
        if numeric_value > 0:
            stats.positive_count += 1
        if numeric_value >= 0:
            stats.nonnegative_count += 1
        if numeric_value == 0:
            stats.zero_count += 1

    def get_numeric_stats(self) -> Iterable[NumericFieldStats]:
        return self._stats.values()

    @staticmethod
    def _build_stats_if_eligible(field_name: str, type_str: str) -> NumericFieldStats | None:
        pure_type, constraint_str = split_type_and_constraint_str(type_str)
        declared = pure_type.strip().lower()
        constraints = parse_constraint_str(constraint_str)

        kind, base = parse_type_annotation(type_str)
        if kind != "scalar" or base not in ("int", "float"):
            return None

        if declared not in (_PLAIN_INT_DECLARED_TYPES | _PLAIN_FLOAT_DECLARED_TYPES):
            return None

        return NumericFieldStats(
            field_name=field_name,
            declared_type=declared,
            type_base=base,
            has_nonnegative_constraint=bool(constraints.get("nonnegative")),
            has_positive_constraint=bool(constraints.get("positive")),
        )
