"""工程自定义检查钩子的协议、加载与执行测试。"""

import json
from pathlib import Path

import pytest
import openpyxl

from ExcelExportTool.core import export_process
from ExcelExportTool.exceptions import ExportError
from ExcelExportTool.hooks.loader import load_checks
from ExcelExportTool.hooks.runner import load_hook_summary, run_custom_hooks


class DummyWorksheet:
    name = "Item"
    source_file = "Item.xlsx"
    data_types = [None, "int", "string"]
    data_labels = [None, "", "required"]
    default_values = [None, None, None]
    headers = [None, "编号", "名称"]
    remarks = [None, "主键", "显示名称"]
    export_data = {1: {"id": 1, "name": "Sword"}}
    export_row_numbers = {1: 7}

    @staticmethod
    def _iter_effective_field_indices():
        return iter((1, 2))

    @staticmethod
    def _actual_field_name(index):
        return ("", "id", "name")[index]


def _write_hook_library(root: Path, checks: list, module_source: str) -> None:
    (root / "checks").mkdir(parents=True)
    (root / "checks" / "__init__.py").write_text("", encoding="utf-8")
    (root / "checks" / "sample.py").write_text(module_source, encoding="utf-8")
    (root / "hooks.json").write_text(
        json.dumps({"api_version": 1, "checks": checks}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_hook_manifest_loads_enabled_checks_in_stable_order(tmp_path):
    _write_hook_library(
        tmp_path,
        [
            {"name": "second", "entry": "checks.sample:second", "order": 20},
            {"name": "disabled", "entry": "checks.sample:disabled", "enabled": False},
            {"name": "first", "entry": "checks.sample:first", "order": 10},
        ],
        "def first(context): return None\n"
        "def second(context): return None\n"
        "def disabled(context): return None\n",
    )

    assert load_hook_summary(str(tmp_path)) == ["first", "second"]


def test_hook_receives_read_only_rows_and_warning_does_not_block(tmp_path):
    _write_hook_library(
        tmp_path,
        ["checks.sample:check_item"],
        "def check_item(context):\n"
        "    sheet = context.require_sheet('Item')\n"
        "    row = sheet.rows[0]\n"
        "    assert row.excel_row == 7\n"
        "    assert row['name'] == 'Sword'\n"
        "    try:\n"
        "        row.values['name'] = 'Changed'\n"
        "    except TypeError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('row values must be read-only')\n"
        "    return context.warning('ITEM_NAME_SAMPLE', '示例警告', file=sheet.source_file, sheet=sheet.name, row=row.excel_row, field='name')\n",
    )

    issues = run_custom_hooks(str(tmp_path), [DummyWorksheet()], str(tmp_path))

    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert issues[0].row == 7


def test_hook_error_blocks_export(tmp_path):
    _write_hook_library(
        tmp_path,
        ["checks.sample:check_item"],
        "def check_item(context):\n"
        "    return context.error('ITEM_INVALID', '物品配置不合法', sheet='Item', row=7)\n",
    )

    with pytest.raises(ExportError, match="未写入本次导出文件"):
        run_custom_hooks(str(tmp_path), [DummyWorksheet()], str(tmp_path))


def test_hook_exception_is_converted_to_blocking_issue(tmp_path):
    _write_hook_library(
        tmp_path,
        ["checks.sample:broken"],
        "def broken(context):\n"
        "    raise RuntimeError('boom')\n",
    )

    with pytest.raises(ExportError, match="1 个错误"):
        run_custom_hooks(str(tmp_path), [DummyWorksheet()], str(tmp_path))


def test_manifest_rejects_unsupported_api_version(tmp_path):
    (tmp_path / "hooks.json").write_text(
        json.dumps({"api_version": 99, "checks": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="api_version"):
        load_checks(str(tmp_path))


def test_batch_hook_error_happens_before_any_export_file_write(monkeypatch, tmp_path):
    hook_root = tmp_path / "hooks"
    _write_hook_library(
        hook_root,
        ["checks.sample:block"],
        "def block(context):\n"
        "    return context.error('TEST_BLOCK', '阻断导出')\n",
    )
    excel_path = tmp_path / "Item.xlsx"
    excel_path.write_bytes(b"placeholder")

    wb = openpyxl.Workbook()
    wb.active.title = "Item"
    monkeypatch.setattr(export_process.openpyxl, "load_workbook", lambda *a, **k: wb)

    class DeferredWorksheet(DummyWorksheet):
        def write_json(self, _output_folder):
            raise AssertionError("hook error must happen before JSON write")

        def generate_script(self, _output_folder):
            raise AssertionError("hook error must happen before C# write")

    monkeypatch.setattr(
        export_process,
        "process_excel_file",
        lambda *args, **kwargs: DeferredWorksheet(),
    )

    with pytest.raises(ExportError, match="未写入本次导出文件"):
        export_process.batch_excel_to_json(
            source_folder=str(tmp_path),
            output_project_folder=str(tmp_path / "output"),
            auto_cleanup=False,
            hook_root=str(hook_root),
        )
