"""Rule #10: suggest unique constraint for list fields."""

from ..collectors import NumericSuggestionCollector
from ..config import MIN_NUMERIC_SAMPLE_COUNT
from ..models import PracticeSuggestion
from .metadata import RuleMetadata


class ListUniqueConstraintRule:
    metadata = RuleMetadata(
        rule_id="list.unique.constraint",
        name="列表去重收束",
        category="constraint-tightening",
        target="list:*",
        output="constraint",
        description="当 list 字段样本中始终无重复元素时，建议增加 unique 约束",
    )

    def evaluate(self, sheet_name: str, collector: NumericSuggestionCollector) -> list[PracticeSuggestion]:
        suggestions: list[PracticeSuggestion] = []
        for item in collector.get_list_stats():
            if item.sample_count < MIN_NUMERIC_SAMPLE_COUNT:
                continue
            if item.has_unique_constraint:
                continue
            if item.all_samples_unique_count != item.sample_count:
                continue

            suggestions.append(
                PracticeSuggestion(
                    rule=self.metadata,
                    sheet_name=sheet_name,
                    field_name=item.field_name,
                    current_type=item.declared_type,
                    suggested_config=f"{item.declared_type}{{unique}}",
                    reason=f"{item.sample_count}/{item.sample_count} 条有效 list 样本均无重复元素",
                )
            )
        return suggestions
