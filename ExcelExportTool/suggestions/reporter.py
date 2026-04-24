"""Suggestion log reporter."""

from typing import Iterable

from ..utils.log import log_success
from .models import PracticeSuggestion


def emit_suggestion_logs(suggestions: Iterable[PracticeSuggestion]) -> None:
    for s in suggestions:
        log_success(
            f"[建议][{s.sheet_name}] 字段 {s.field_name} 当前类型 {s.current_type}，"
            f"可考虑改为 {s.suggested_type}（{s.reason}）"
        )
