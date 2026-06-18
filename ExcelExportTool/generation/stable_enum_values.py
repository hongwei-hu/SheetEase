"""Stable enum value allocation backed by a project-local manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence

from ..exceptions import ExportError


STABLE_ENUM_VALUES_FILENAME = ".stable_enum_values.json"


class StableEnumValueAllocator:
    """Allocate enum values without shifting existing implicit values."""

    def __init__(self, manifest_path: Path, bootstrap_dirs: Optional[Sequence[Optional[Path]]] = None) -> None:
        self.manifest_path = manifest_path
        self._loaded_from_manifest = manifest_path.exists()
        if manifest_path.exists():
            self._values: Dict[str, Dict[str, int]] = self._load(manifest_path)
            self._dirty = False
        else:
            self._values = self._load_generated_enum_values(bootstrap_dirs or [])
            self._dirty = bool(self._values)

    @staticmethod
    def _load(path: Path) -> Dict[str, Dict[str, int]]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ExportError(f"stable enum manifest 读取失败: {path} -> {exc}") from exc
        if not isinstance(raw, dict):
            raise ExportError(f"stable enum manifest 格式错误: {path} 顶层必须是对象")

        result: Dict[str, Dict[str, int]] = {}
        for enum_name, items in raw.items():
            if not isinstance(enum_name, str) or not isinstance(items, dict):
                raise ExportError(f"stable enum manifest 格式错误: {path} 中 {enum_name!r} 必须是对象")
            result[enum_name] = {}
            for item_name, value in items.items():
                if not isinstance(item_name, str) or isinstance(value, bool) or not isinstance(value, int):
                    raise ExportError(
                        f"stable enum manifest 格式错误: {path} 中 {enum_name}.{item_name} 必须是整数"
                    )
                result[enum_name][item_name] = value
        return result

    @staticmethod
    def _load_generated_enum_values(paths: Sequence[Optional[Path]]) -> Dict[str, Dict[str, int]]:
        result: Dict[str, Dict[str, int]] = {}
        for raw_path in paths:
            if raw_path is None:
                continue
            path = Path(raw_path)
            if not path.exists() or not path.is_dir():
                continue
            for cs_path in path.rglob("*.cs"):
                for enum_name, items in StableEnumValueAllocator._parse_generated_enum_file(cs_path).items():
                    existing = result.get(enum_name)
                    if existing is not None and existing != items:
                        raise ExportError(
                            f"stable enum bootstrap 冲突: {enum_name} 在多个生成文件中定义不一致"
                        )
                    result[enum_name] = items
        return result

    @staticmethod
    def _parse_generated_enum_file(path: Path) -> Dict[str, Dict[str, int]]:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            raise ExportError(f"stable enum bootstrap 读取失败: {path} -> {exc}") from exc

        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        enums: Dict[str, Dict[str, int]] = {}
        for match in re.finditer(r"\benum\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{(.*?)\}", text, flags=re.S):
            enum_name = match.group(1)
            body = match.group(2)
            items: Dict[str, int] = {}
            for member_text in body.split(","):
                member_text = re.sub(r"//.*", "", member_text).strip()
                if not member_text:
                    continue
                member_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([+-]?\d+)$", member_text)
                if member_match is None:
                    continue
                item_name = member_match.group(1)
                item_value = int(member_match.group(2))
                if item_value in items.values():
                    raise ExportError(
                        f"stable enum bootstrap 发现重复值: {path} 中 {enum_name}.{item_name}={item_value}"
                    )
                items[item_name] = item_value
            if items:
                enums[enum_name] = items
        return enums

    def allocate(
        self,
        enum_name: str,
        item_names: Iterable[str],
        explicit_values: Mapping[str, Optional[int]],
        default_values: Mapping[str, int],
        source: str,
    ) -> Dict[str, int]:
        ordered_names = list(item_names)
        if not ordered_names:
            return {}

        all_explicit = all(explicit_values.get(name) is not None for name in ordered_names)
        if all_explicit:
            if not self._loaded_from_manifest and enum_name in self._values:
                del self._values[enum_name]
                self._dirty = True
            return self._resolve_all_explicit(enum_name, ordered_names, explicit_values, source)

        stable_items = self._values.get(enum_name, {})
        result: Dict[str, int] = {}
        used_values = set(stable_items.values())
        used_values.update(
            value for value in explicit_values.values()
            if value is not None
        )
        explicit_owner_by_value: Dict[int, str] = {}

        for name in ordered_names:
            value = explicit_values.get(name)
            if value is None:
                continue
            previous_owner = explicit_owner_by_value.get(value)
            if previous_owner is not None:
                raise ExportError(
                    f"duplicate enum value in {source}: {name}={value} conflicts with "
                    f"{previous_owner}. Enum values must be unique."
                )
            explicit_owner_by_value[value] = name

            historical_value = stable_items.get(name)
            if historical_value is not None and historical_value != value:
                raise ExportError(
                    f"stable enum value conflict in {source}: {enum_name}.{name} explicitly uses {value}, "
                    f"but stable enum value is {historical_value}."
                )

            historical_owner = self._owner_of_value(stable_items, value)
            if historical_owner is not None and historical_owner != name:
                raise ExportError(
                    f"stable enum value conflict in {source}: {enum_name}.{name} explicitly uses {value}, "
                    f"but it conflicts with stable enum value {enum_name}.{historical_owner}={value}."
                )
            result[name] = value

        for name in ordered_names:
            if name in result:
                continue

            historical_value = stable_items.get(name)
            if historical_value is not None:
                explicit_owner = explicit_owner_by_value.get(historical_value)
                if explicit_owner is not None and explicit_owner != name:
                    raise ExportError(
                        f"stable enum value conflict in {source}: {enum_name}.{name} keeps "
                        f"stable enum value {historical_value}, but {explicit_owner} explicitly uses it."
                    )
                result[name] = historical_value
                continue

            candidate = self._next_free_value(used_values) if stable_items else default_values[name]
            explicit_owner = explicit_owner_by_value.get(candidate)
            if explicit_owner is not None:
                raise ExportError(
                    f"default enum value conflict in {source}: {enum_name}.{name} would default to {candidate}, "
                    f"but {explicit_owner} explicitly uses it."
                )
            if candidate in used_values:
                candidate = self._next_free_value(used_values)
            result[name] = candidate
            used_values.add(candidate)

        merged_items = dict(stable_items)
        merged_items.update(result)
        if merged_items != stable_items:
            self._values[enum_name] = merged_items
            self._dirty = True
        return result

    @staticmethod
    def _resolve_all_explicit(
        enum_name: str,
        item_names: Iterable[str],
        explicit_values: Mapping[str, Optional[int]],
        source: str,
    ) -> Dict[str, int]:
        result: Dict[str, int] = {}
        owner_by_value: Dict[int, str] = {}
        for name in item_names:
            value = explicit_values[name]
            if value is None:
                raise ExportError(f"stable enum internal error in {source}: {enum_name}.{name} has no explicit value")
            owner = owner_by_value.get(value)
            if owner is not None:
                raise ExportError(
                    f"duplicate enum value in {source}: {name}={value} conflicts with "
                    f"{owner}. Enum values must be unique."
                )
            owner_by_value[value] = name
            result[name] = value
        return result

    @staticmethod
    def _owner_of_value(items: Mapping[str, int], value: int) -> Optional[str]:
        for name, item_value in items.items():
            if item_value == value:
                return name
        return None

    @staticmethod
    def _next_free_value(used_values: set[int]) -> int:
        value = max(used_values) + 1 if used_values else 0
        while value in used_values:
            value += 1
        return value

    def save(self) -> None:
        if not self._dirty:
            return
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self._values, ensure_ascii=False, indent=2, sort_keys=True)
        self.manifest_path.write_text(content + "\n", encoding="utf-8")
