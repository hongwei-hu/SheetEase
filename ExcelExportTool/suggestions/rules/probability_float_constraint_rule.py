"""Rule #1: suggest tighter probability constraint for float fields."""

from ..collectors import NumericSuggestionCollector
from ..config import MIN_NUMERIC_SAMPLE_COUNT
from ..models import PracticeSuggestion
from .metadata import RuleMetadata


class ProbabilityFloatConstraintRule:
    metadata = RuleMetadata(
        rule_id="numeric.float.probability.constraint",
        name="概率浮点收束",
        category="constraint-tightening",
        target="scalar:float",
        output="constraint",
        description="当 float 字段全量值落在 [0,1] 时，建议增加概率约束",
    )

    def evaluate(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        suggestions: list[PracticeSuggestion] = []
        for item in collector.get_numeric_stats():
            if item.type_base != "float":
                continue
            if item.sample_count < MIN_NUMERIC_SAMPLE_COUNT:
                continue
            if item.in_unit_interval_count != item.sample_count:
                continue
            if item.has_min_zero_max_one_constraint:
                continue

            suggestions.append(
                PracticeSuggestion(
                    rule=self.metadata,
                    sheet_name=sheet_name,
                    field_name=item.field_name,
                    current_type=item.declared_type,
                    suggested_config="float{min:0,max:1}",
                    reason=f"{item.sample_count}/{item.sample_count} 条有效值均落在 [0,1]",
                )
            )
        return suggestions
