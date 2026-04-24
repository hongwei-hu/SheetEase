"""Rules for recommending concise numeric scalar types."""

from typing import Iterable

from ..collectors import NumericFieldStats
from ..config import MIN_NUMERIC_SAMPLE_COUNT
from ..models import PracticeSuggestion


class NumericTypeSuggestionRule:
    """Suggest pint/nnint/pfloat/nnfloat based on observed data distribution."""

    def evaluate(self, sheet_name: str, stats: Iterable[NumericFieldStats]) -> list[PracticeSuggestion]:
        suggestions: list[PracticeSuggestion] = []
        for item in stats:
            if item.sample_count < MIN_NUMERIC_SAMPLE_COUNT:
                continue
            if item.has_positive_constraint or item.has_nonnegative_constraint:
                continue

            if item.type_base == "int":
                suggestion = self._suggest_int(sheet_name, item)
            elif item.type_base == "float":
                suggestion = self._suggest_float(sheet_name, item)
            else:
                suggestion = None

            if suggestion is not None:
                suggestions.append(suggestion)
        return suggestions

    @staticmethod
    def _suggest_int(sheet_name: str, item: NumericFieldStats) -> PracticeSuggestion | None:
        if item.positive_count == item.sample_count:
            return PracticeSuggestion(
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_type="pint",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 > 0",
            )

        if item.nonnegative_count == item.sample_count and item.zero_count > 0:
            return PracticeSuggestion(
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_type="nnint",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 >= 0，且包含 0",
            )
        return None

    @staticmethod
    def _suggest_float(sheet_name: str, item: NumericFieldStats) -> PracticeSuggestion | None:
        if item.positive_count == item.sample_count:
            return PracticeSuggestion(
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_type="pfloat",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 > 0",
            )

        if item.nonnegative_count == item.sample_count and item.zero_count > 0:
            return PracticeSuggestion(
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_type="nnfloat",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 >= 0，且包含 0",
            )
        return None
