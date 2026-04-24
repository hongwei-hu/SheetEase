"""Practice suggestions package."""

from .collectors import NumericSuggestionCollector
from .config import ENABLE_PRACTICE_SUGGESTIONS
from .engine import SuggestionEngine
from .reporter import emit_suggestion_logs

__all__ = [
    "ENABLE_PRACTICE_SUGGESTIONS",
    "NumericSuggestionCollector",
    "SuggestionEngine",
    "emit_suggestion_logs",
]
