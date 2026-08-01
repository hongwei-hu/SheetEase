# Author: huhongwei 306463233@qq.com
# Created: 2024-09-10
# MIT License

"""完整导表 CLI，以及供打包程序复用的无界面自动化入口。"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO

from ..exceptions import ExportError
from .export_process import batch_excel_to_json


EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 2
EXIT_EXPORT_ERROR = 3
EXIT_INTERNAL_ERROR = 4
EXIT_INTERRUPTED = 130
REPORT_SCHEMA_VERSION = 1
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


class ConfigError(Exception):
    """命令行配置或参数无法用于启动导出。"""


class TeeTextIO(io.TextIOBase):
    """同时保留原控制台输出和自动化报告所需的文本副本。"""

    def __init__(self, target: Optional[TextIO], capture: io.StringIO):
        self._target = target
        self._capture = capture

    def write(self, text: str) -> int:
        self._capture.write(text)
        if self._target is not None:
            try:
                self._target.write(text)
            except (OSError, ValueError):
                # PyInstaller --noconsole 在 Windows 上可能提供不可写的占位句柄。
                self._target = None
        return len(text)

    def flush(self) -> None:
        self._capture.flush()
        if self._target is not None:
            try:
                self._target.flush()
            except (OSError, ValueError):
                self._target = None


def _contains_assets(*paths: str) -> bool:
    return any(path and "assets" in str(path).replace("\\", "/").lower() for path in paths)


def _is_writable_dir(path_value: str) -> bool:
    try:
        if not path_value:
            return False
        os.makedirs(path_value, exist_ok=True)
        testfile = Path(path_value) / ".sheetease_write_test.tmp"
        testfile.write_text("ok", encoding="utf-8")
        testfile.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _excel_count(excel_root: str) -> int:
    try:
        root = Path(excel_root)
        if not root.is_dir():
            return 0
        return sum(
            1
            for path in root.rglob("*.xlsx")
            if path.name and path.name[0].isupper() and not path.name.startswith("~$")
        )
    except Exception:
        return 0


def _strict_validate(cfg: dict, force_no_assets: bool = False) -> tuple[bool, str]:
    """校验导出所需路径；force_no_assets 仅为旧调用兼容参数。"""
    del force_no_assets
    excel_root = str(cfg.get("excel_root", "") or "")
    if not excel_root or not Path(excel_root).is_dir():
        return False, f"Excel 根目录不存在: {excel_root}"
    if _excel_count(excel_root) <= 0:
        return False, "表格目录没有任何符合导出规范的表格。命名规则：扩展名 .xlsx，文件名首字母需大写，不以 ~$ 开头"
    for key in ("output_project", "cs_output", "enum_output"):
        value = str(cfg.get(key, "") or "")
        if not value:
            return False, f"配置缺少或为空: {key}"
        if not _is_writable_dir(value):
            return False, f"输出目录不可写: {value}"
    hook_root = str(cfg.get("custom_hook_root", "") or "").strip()
    if hook_root and not Path(hook_root).is_dir():
        return False, f"自定义检查钩子目录不存在: {hook_root}"
    return True, ""


def _load_config_from_candidates() -> tuple[Optional[dict], Optional[Path]]:
    candidates = [
        Path.cwd() / "sheet_config.json",
        Path(__file__).resolve().parents[1] / "sheet_config.json",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return json.loads(candidate.read_text(encoding="utf-8")), candidate
        except Exception:
            continue
    return None, None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SheetEase",
        description="将 Excel 配置导出为 JSON 与 C#，并运行内置及工程自定义检查。",
    )
    parser.add_argument("paths", nargs="*", metavar="PATH", help="旧版四路径参数：Excel、JSON、C#、枚举输出目录")
    parser.add_argument("--config", "-c", help="sheet_config.json 路径")
    parser.add_argument("--no-diff", action="store_true", help="即使内容未变化也重新写入")
    parser.add_argument("--dry-run", action="store_true", help="完成解析与检查，但不写入导出产物")
    parser.add_argument("--no-cleanup", action="store_true", help="不检查和清理未在本次生成的旧产物")
    parser.add_argument("--force-no-assets", action="store_true", help="兼容旧参数；非 Assets 路径当前只警告")
    parser.add_argument("--headless", action="store_true", help="禁止 GUI 回退，适合自动化和代理执行")
    parser.add_argument("--report", help="写入 UTF-8 JSON 运行报告；失败时也会尽力写入")
    return parser


def _load_config(options: argparse.Namespace) -> tuple[dict, Optional[Path]]:
    def ensure_object(value: Any, source: str) -> dict:
        if not isinstance(value, dict):
            raise ConfigError(f"配置文件根节点必须是 JSON 对象: {source}")
        return value

    if options.config:
        cfg_path = Path(options.config).expanduser().resolve()
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            return ensure_object(cfg, str(cfg_path)), cfg_path
        except Exception as exc:
            if options.headless:
                raise ConfigError(f"无法读取配置文件: {cfg_path} -> {exc}") from exc

            print(f"未找到或无法读取配置: {cfg_path}. 将启动 GUI 进行配置...")
            try:
                from .. import app_main as gui

                gui.main()
            except Exception as gui_exc:
                raise ConfigError(f"启动 GUI 失败: {gui_exc}") from gui_exc

            root_cfg = Path(__file__).resolve().parents[1] / "sheet_config.json"
            if not root_cfg.exists():
                raise ConfigError("未检测到已保存的配置文件，请在 GUI 中点击“保存配置”后重试。")
            try:
                cfg = ensure_object(json.loads(root_cfg.read_text(encoding="utf-8")), str(root_cfg))
                try:
                    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return cfg, root_cfg
            except Exception as root_exc:
                raise ConfigError(f"读取 GUI 保存的配置失败: {root_exc}") from root_exc

    if len(options.paths) == 4:
        return {
            "excel_root": options.paths[0],
            "output_project": options.paths[1],
            "cs_output": options.paths[2],
            "enum_output": options.paths[3],
        }, None
    if options.paths:
        raise ConfigError("旧版位置参数必须恰好提供 4 个路径；也可以改用 --config <file>。")

    cfg, cfg_path = _load_config_from_candidates()
    if cfg is None:
        raise ConfigError("未找到配置。请提供 --config <file>，或在当前目录放置 sheet_config.json。")
    return ensure_object(cfg, str(cfg_path or "sheet_config.json")), cfg_path


def _issue_to_dict(issue: Any) -> dict:
    if dataclasses.is_dataclass(issue):
        return dataclasses.asdict(issue)
    if isinstance(issue, dict):
        return dict(issue)
    return {"severity": "error", "code": "UNSTRUCTURED_ISSUE", "message": str(issue)}


def _error_to_dict(exc: BaseException) -> dict:
    result = {
        "type": type(exc).__name__,
        "message": str(exc),
    }
    context = getattr(exc, "context", None)
    if isinstance(context, dict) and context:
        result["context"] = dict(context)
    issues = getattr(exc, "issues", None)
    if issues:
        result["issues"] = [_issue_to_dict(issue) for issue in issues]
    return result


def _config_snapshot(cfg: Optional[dict]) -> dict:
    if not cfg:
        return {}
    keys = ("excel_root", "output_project", "cs_output", "enum_output", "custom_hook_root")
    return {key: cfg.get(key) for key in keys if key in cfg}


def _atomic_write_report(path_value: str, report: dict) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)
    return path


def _report_path_from_argv(argv: Sequence[str]) -> Optional[str]:
    for index, value in enumerate(argv):
        if value == "--report" and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith("--report="):
            return value.split("=", 1)[1]
    return None


def _run(options: argparse.Namespace) -> tuple[int, Optional[dict], Optional[dict], Optional[dict]]:
    cfg: Optional[dict] = None
    try:
        cfg, cfg_path = _load_config(options)
        ok, message = _strict_validate(cfg, force_no_assets=options.force_no_assets)
        if not ok:
            raise ConfigError(message)

        os.environ["SHEETEASE_CONFIG_JSON"] = json.dumps(cfg, ensure_ascii=False)
        if cfg_path is not None:
            os.environ["SHEETEASE_CONFIG_PATH"] = str(cfg_path)

        if not _contains_assets(cfg.get("output_project", ""), cfg.get("cs_output", ""), cfg.get("enum_output", "")):
            print("[Warn] 输出路径未包含 'Assets'，这通常不是 Unity 工程的 Assets 子目录（将继续导表）")

        summary = batch_excel_to_json(
            cfg["excel_root"],
            output_client_folder=None,
            output_project_folder=cfg["output_project"],
            csfile_output_folder=cfg["cs_output"],
            enum_output_folder=cfg["enum_output"],
            diff_only=not options.no_diff,
            dry_run=options.dry_run,
            auto_cleanup=not options.no_cleanup,
            hook_root=cfg.get("custom_hook_root") or None,
            table_profiles=cfg.get("table_profiles") or None,
        )
        summary_dict = summary.to_dict() if hasattr(summary, "to_dict") else None
        return EXIT_SUCCESS, cfg, summary_dict, None
    except ConfigError as exc:
        print(f"配置无效：{exc}")
        return EXIT_CONFIG_ERROR, cfg, None, _error_to_dict(exc)
    except ExportError as exc:
        print(f"导出或检查失败：{exc}")
        return EXIT_EXPORT_ERROR, cfg, None, _error_to_dict(exc)
    except KeyboardInterrupt as exc:
        print("导出已被中断。")
        return EXIT_INTERRUPTED, cfg, None, _error_to_dict(exc)
    except Exception as exc:
        print(f"导出发生未预期错误：{type(exc).__name__}: {exc}")
        return EXIT_INTERNAL_ERROR, cfg, None, _error_to_dict(exc)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """执行 CLI 并返回稳定退出码；默认调用仍保留完整的人类可读日志。"""
    args = list(sys.argv[1:] if argv is None else argv)
    report_path = _report_path_from_argv(args)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    capture = io.StringIO()
    stdout_tee = TeeTextIO(sys.stdout, capture)
    stderr_tee = TeeTextIO(sys.stderr, capture)
    options: Optional[argparse.Namespace] = None
    cfg: Optional[dict] = None
    summary: Optional[dict] = None
    error: Optional[dict] = None
    exit_code = EXIT_INTERNAL_ERROR

    with contextlib.redirect_stdout(stdout_tee), contextlib.redirect_stderr(stderr_tee):
        try:
            options = _parser().parse_args(args)
            exit_code, cfg, summary, error = _run(options)
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
            if exit_code:
                error = {"type": "ArgumentError", "message": "命令行参数无效"}

    finished_at = datetime.now(timezone.utc)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": "SheetEase",
        "mode": "check" if options and options.dry_run else "export",
        "status": "succeeded" if exit_code == EXIT_SUCCESS else "failed",
        "exit_code": exit_code,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(max(0.0, time.perf_counter() - started), 6),
        "options": {
            "headless": bool(options and options.headless),
            "dry_run": bool(options and options.dry_run),
            "diff_only": not bool(options and options.no_diff),
            "auto_cleanup": not bool(options and options.no_cleanup),
        },
        "config": _config_snapshot(cfg),
        "summary": summary,
        "error": error,
        "log": ANSI_ESCAPE_RE.sub("", capture.getvalue()),
    }

    if report_path:
        try:
            written = _atomic_write_report(report_path, report)
            if sys.stdout is not None:
                try:
                    print(f"SHEETEASE_REPORT={written}")
                except (OSError, ValueError):
                    pass
        except Exception as exc:
            if sys.stderr is not None:
                try:
                    print(f"无法写入自动化报告: {exc}", file=sys.stderr)
                except (OSError, ValueError):
                    pass
            if exit_code == EXIT_SUCCESS:
                exit_code = EXIT_INTERNAL_ERROR

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
