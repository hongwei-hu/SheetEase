"""Stable, read-only data model exposed to project hook code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional


HOOK_API_VERSION = 1
VALID_SEVERITIES = frozenset({"error", "warning", "info"})


def deep_freeze(value: Any) -> Any:
    """Recursively convert exporter-owned containers into read-only values."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class HookIssue:
    severity: str
    code: str
    message: str
    file: Optional[str] = None
    sheet: Optional[str] = None
    row: Optional[int] = None
    field: Optional[str] = None
    suggestion: Optional[str] = None

    def __post_init__(self) -> None:
        severity = str(self.severity).strip().lower()
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"unsupported hook issue severity: {self.severity!r}")
        if not str(self.code).strip():
            raise ValueError("hook issue code must not be empty")
        if not str(self.message).strip():
            raise ValueError("hook issue message must not be empty")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "code", str(self.code).strip())
        object.__setattr__(self, "message", str(self.message).strip())


@dataclass(frozen=True)
class HookField:
    name: str
    declared_type: str
    label: str
    default: Any
    header: Any
    remark: Any
    column: int


@dataclass(frozen=True)
class HookRow:
    key: Any
    excel_row: int
    values: Mapping[str, Any]

    def get(self, field: str, default: Any = None) -> Any:
        return self.values.get(field, default)

    def __getitem__(self, field: str) -> Any:
        return self.values[field]


@dataclass(frozen=True)
class HookSheet:
    name: str
    source_file: str
    fields: tuple[HookField, ...]
    rows: tuple[HookRow, ...]

    def find_by_id(self, value: Any) -> Optional[HookRow]:
        return next((row for row in self.rows if row.key == value or row.get("id") == value), None)


@dataclass(frozen=True)
class HookContext:
    api_version: int
    source_root: Path
    hook_root: Path
    sheets: Mapping[str, HookSheet]
    config: Mapping[str, Any]

    def get_sheet(self, name: str) -> Optional[HookSheet]:
        return self.sheets.get(name)

    def require_sheet(self, name: str) -> HookSheet:
        sheet = self.get_sheet(name)
        if sheet is None:
            raise KeyError(f"sheet not found: {name}")
        return sheet

    @staticmethod
    def issue(severity: str, code: str, message: str, **location: Any) -> HookIssue:
        return HookIssue(severity=severity, code=code, message=message, **location)

    @staticmethod
    def error(code: str, message: str, **location: Any) -> HookIssue:
        return HookIssue("error", code, message, **location)

    @staticmethod
    def warning(code: str, message: str, **location: Any) -> HookIssue:
        return HookIssue("warning", code, message, **location)

    @staticmethod
    def info(code: str, message: str, **location: Any) -> HookIssue:
        return HookIssue("info", code, message, **location)


def build_hook_context(
    worksheets: Iterable[Any],
    source_root: str,
    hook_root: str,
    config: Optional[Mapping[str, Any]] = None,
) -> HookContext:
    sheets: dict[str, HookSheet] = {}
    for worksheet in worksheets:
        export_data = getattr(worksheet, "export_data", None)
        if export_data is None:
            raise RuntimeError(f"sheet {worksheet.name} has not built export data")

        fields: list[HookField] = []
        for index in worksheet._iter_effective_field_indices():
            fields.append(HookField(
                name=worksheet._actual_field_name(index),
                declared_type=str(worksheet.data_types[index] or ""),
                label=str(worksheet.data_labels[index] or ""),
                default=deep_freeze(worksheet.default_values[index]),
                header=deep_freeze(worksheet.headers[index]),
                remark=deep_freeze(worksheet.remarks[index]),
                column=index + 1,
            ))

        row_numbers = getattr(worksheet, "export_row_numbers", {})
        rows = tuple(
            HookRow(key=key, excel_row=int(row_numbers.get(key, 0)), values=deep_freeze(value))
            for key, value in export_data.items()
            if key != "_meta"
        )
        source_file = str(getattr(worksheet, "source_file", "") or "")
        sheets[worksheet.name] = HookSheet(
            name=worksheet.name,
            source_file=source_file,
            fields=tuple(fields),
            rows=rows,
        )

    return HookContext(
        api_version=HOOK_API_VERSION,
        source_root=Path(source_root).resolve(),
        hook_root=Path(hook_root).resolve(),
        sheets=MappingProxyType(sheets),
        config=deep_freeze(dict(config or {})),
    )
