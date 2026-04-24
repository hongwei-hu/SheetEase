"""Rules for recommending concise numeric scalar types."""

from ..collectors import NumericFieldStats, NumericSuggestionCollector
from ..config import MIN_NUMERIC_SAMPLE_COUNT
from ..models import PracticeSuggestion
from .metadata import RuleMetadata


class NumericTypeSuggestionRule:
    """Suggest pint/nnint/pfloat/nnfloat based on observed data distribution."""

    metadata = RuleMetadata(
        rule_id="numeric.scalar.tighten.nn_or_p",
        name="数值标量类型收束",
        category="type-variant",
        target="scalar:int/float",
        output="type",
        description="根据值分布建议 nnint/nnfloat/pint/pfloat",
    )

    def evaluate(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        stats = collector.get_numeric_stats()
        suggestions: list[PracticeSuggestion] = []
        for item in stats:
            if item.sample_count < MIN_NUMERIC_SAMPLE_COUNT:
                continue
            if item.has_positive_constraint or item.has_nonnegative_constraint:
                continue
            if item.type_base == "float" and item.in_unit_interval_count == item.sample_count:
                # 交给概率收束规则处理，避免重复建议。
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
                rule=NumericTypeSuggestionRule.metadata,
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_config="pint",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 > 0",
            )

        if item.nonnegative_count == item.sample_count and item.zero_count > 0:
            return PracticeSuggestion(
                rule=NumericTypeSuggestionRule.metadata,
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_config="nnint",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 >= 0，且包含 0",
            )
        return None

    @staticmethod
    def _suggest_float(sheet_name: str, item: NumericFieldStats) -> PracticeSuggestion | None:
        if item.positive_count == item.sample_count:
            return PracticeSuggestion(
                rule=NumericTypeSuggestionRule.metadata,
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_config="pfloat",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 > 0",
            )

        if item.nonnegative_count == item.sample_count and item.zero_count > 0:
            return PracticeSuggestion(
                rule=NumericTypeSuggestionRule.metadata,
                sheet_name=sheet_name,
                field_name=item.field_name,
                current_type=item.declared_type,
                suggested_config="nnfloat",
                reason=f"{item.sample_count}/{item.sample_count} 条有效值均 >= 0，且包含 0",
            )
        return None
