"""Manifest-driven loader for trusted project hook modules."""

from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from .models import HOOK_API_VERSION


HOOK_MANIFEST_FILENAME = "hooks.json"
_KNOWN_HOOK_ROOTS: set[Path] = set()


@dataclass(frozen=True)
class LoadedCheck:
    name: str
    entry: str
    order: int
    function: Callable[..., Any]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


@contextmanager
def hook_import_path(root: Path) -> Iterator[None]:
    root_text = str(root)
    inserted = root_text not in sys.path
    previous_dont_write_bytecode = sys.dont_write_bytecode
    if inserted:
        sys.path.insert(0, root_text)
    # 工程检查库通常与 Excel 资源一同版本管理，不在其中留下 __pycache__。
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if inserted:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass


def _clear_cached_hook_modules(root: Path) -> None:
    for module_name, module in list(sys.modules.items()):
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        try:
            if _is_within(Path(module_file), root):
                sys.modules.pop(module_name, None)
        except (OSError, TypeError, ValueError):
            continue


def _read_manifest(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"hook directory does not exist: {root}")
    manifest_path = root / HOOK_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ValueError(f"hook manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to read hook manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("hook manifest root must be a JSON object")
    if manifest.get("api_version") != HOOK_API_VERSION:
        raise ValueError(
            f"unsupported hook api_version {manifest.get('api_version')!r}; expected {HOOK_API_VERSION}"
        )
    if not isinstance(manifest.get("checks"), list):
        raise ValueError("hook manifest checks must be an array")
    return manifest


def load_checks(root_path: str) -> list[LoadedCheck]:
    root = Path(root_path).resolve()
    manifest = _read_manifest(root)
    definitions: list[tuple[int, int, str, str]] = []
    for index, raw in enumerate(manifest["checks"]):
        if isinstance(raw, str):
            entry, name, order, enabled = raw, raw, index, True
        elif isinstance(raw, dict):
            entry = raw.get("entry")
            name = raw.get("name") or entry
            order = raw.get("order", index)
            enabled = raw.get("enabled", True)
        else:
            raise ValueError(f"checks[{index}] must be a string or object")
        if not enabled:
            continue
        if not isinstance(entry, str) or ":" not in entry:
            raise ValueError(f"checks[{index}].entry must use 'module.path:function' format")
        try:
            order_value = int(order)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"checks[{index}].order must be an integer") from exc
        definitions.append((order_value, index, str(name), entry))

    importlib.invalidate_caches()
    for known_root in tuple(_KNOWN_HOOK_ROOTS | {root}):
        _clear_cached_hook_modules(known_root)
    _KNOWN_HOOK_ROOTS.add(root)
    loaded: list[LoadedCheck] = []
    with hook_import_path(root):
        for order, _index, name, entry in sorted(definitions):
            module_name, function_name = entry.split(":", 1)
            if not module_name or not function_name:
                raise ValueError(f"invalid hook entry: {entry}")
            module = importlib.import_module(module_name)
            module_file = getattr(module, "__file__", None)
            if not module_file or not _is_within(Path(module_file), root):
                raise ValueError(f"hook module must be located under hook directory: {entry}")
            function = getattr(module, function_name, None)
            if not callable(function):
                raise ValueError(f"hook entry is not callable: {entry}")
            loaded.append(LoadedCheck(name=name, entry=entry, order=order, function=function))
    return loaded
