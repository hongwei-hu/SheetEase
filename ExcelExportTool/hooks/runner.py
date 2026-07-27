"""Execution and reporting for custom project checks."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Mapping, Optional

from ..exceptions import ExportError
from ..utils.log import log_error, log_info, log_sep, log_warn
from .loader import hook_import_path, load_checks
from .models import HookContext, HookIssue, build_hook_context


def load_hook_summary(hook_root: str) -> list[str]:
    """Load a hook directory and return enabled check names for GUI diagnostics."""
    return [check.name for check in load_checks(hook_root)]


def _normalize_results(value: Any) -> list[HookIssue]:
    if value is None:
        return []
    if isinstance(value, HookIssue):
        return [value]
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("hook must return HookIssue, an iterable of HookIssue, or None")
    result = list(value)
    invalid = next((item for item in result if not isinstance(item, HookIssue)), None)
    if invalid is not None:
        raise TypeError(f"hook returned unsupported result item: {type(invalid).__name__}")
    return result


def _location_text(issue: HookIssue) -> str:
    parts = []
    if issue.file:
        parts.append(issue.file)
    if issue.sheet:
        parts.append(issue.sheet)
    if issue.row is not None:
        parts.append(f"行{issue.row}")
    if issue.field:
        parts.append(f"字段 {issue.field}")
    return f" ({' / '.join(parts)})" if parts else ""


def run_custom_hooks(
    hook_root: str,
    worksheets: list[Any],
    source_root: str,
    config: Optional[Mapping[str, Any]] = None,
) -> list[HookIssue]:
    root = Path(hook_root).resolve()
    try:
        checks = load_checks(str(root))
        context: HookContext = build_hook_context(worksheets, source_root, str(root), config)
    except Exception as exc:
        raise ExportError(f"自定义检查钩子加载失败: {exc}") from exc

    log_sep("自定义检查阶段")
    log_info(f"钩子目录: {root}")
    log_info(f"已加载 {len(checks)} 个自定义检查")
    issues: list[HookIssue] = []
    with hook_import_path(root):
        for check in checks:
            log_info(f"运行检查: {check.name} ({check.entry})")
            try:
                issues.extend(_normalize_results(check.function(context)))
            except Exception as exc:
                issue = context.error(
                    "HOOK_EXECUTION_FAILED",
                    f"检查 {check.name} 运行失败: {type(exc).__name__}: {exc}",
                )
                issues.append(issue)

    for issue in issues:
        text = f"[{issue.code}] {issue.message}{_location_text(issue)}"
        if issue.suggestion:
            text += f"；建议: {issue.suggestion}"
        if issue.severity == "error":
            log_error(text)
        elif issue.severity == "warning":
            log_warn(text)
        else:
            log_info(text)

    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    log_info(f"自定义检查完成: 错误 {errors}，警告 {warnings}，总问题 {len(issues)}")
    if errors:
        raise ExportError(f"自定义检查未通过，共 {errors} 个错误；未写入本次导出文件")
    return issues
