"""WorksheetData 核心行为测试。"""

import json

import openpyxl
import pytest

from ExcelExportTool.core.worksheet_data import WorksheetData
from ExcelExportTool.exceptions import ConstraintViolationError
from ExcelExportTool.generation.enum_registry import get_enum_registry, reset_enum_registry


def _set_row(ws, row_idx, values):
    for i, v in enumerate(values, start=1):
        ws.cell(row=row_idx, column=i, value=v)


def _build_min_sheet(sheet_name="Item"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    # A 列占位，数据从 B 列开始
    _set_row(ws, 1, ["", "备注id", "备注字段"])
    _set_row(ws, 2, ["", "id", "字段"])
    _set_row(ws, 3, ["", "int", "int"])
    _set_row(ws, 4, ["", "", ""])
    _set_row(ws, 5, ["", "id", "value"])
    _set_row(ws, 6, ["", None, None])
    return ws


def test_required_missing_raises(monkeypatch, tmp_path):
    import ExcelExportTool.core.worksheet_data as mod
    monkeypatch.setattr(mod, "check_interface_field_types", lambda *a, **k: None)

    ws = _build_min_sheet("ReqCase")
    _set_row(ws, 4, ["", "", "required"])
    _set_row(ws, 7, ["", 1, None])

    data = WorksheetData(ws)
    with pytest.raises(RuntimeError, match="required"):
        data.generate_json(str(tmp_path))


def test_constraint_violation_raises(monkeypatch, tmp_path):
    import ExcelExportTool.core.worksheet_data as mod
    monkeypatch.setattr(mod, "check_interface_field_types", lambda *a, **k: None)

    ws = _build_min_sheet("ConstraintCase")
    _set_row(ws, 3, ["", "int", "int{min:1,max:5}"])
    _set_row(ws, 7, ["", 1, 9])

    data = WorksheetData(ws)
    with pytest.raises(ConstraintViolationError):
        data.generate_json(str(tmp_path))


def test_default_value_applied_and_meta_tags(monkeypatch, tmp_path):
    import ExcelExportTool.core.worksheet_data as mod
    monkeypatch.setattr(mod, "check_interface_field_types", lambda *a, **k: None)

    ws = _build_min_sheet("MetaCase")
    _set_row(ws, 3, ["", "int", "string"])
    _set_row(ws, 5, ["", "id", "[Asset:png]icon"])
    _set_row(ws, 6, ["", None, "DefaultIcon"])
    _set_row(ws, 7, ["", 1, None])

    data = WorksheetData(ws)
    data.generate_json(str(tmp_path))

    out_file = tmp_path / "MetaCaseConfig.json"
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert content["1"]["icon"] == "DefaultIcon"
    assert content["_meta"]["fields"]["icon"]["tags"] == ["asset:png"]


def test_optional_enum_field_allows_empty_and_emits_nullable_type(monkeypatch, tmp_path):
    import ExcelExportTool.core.worksheet_data as mod
    monkeypatch.setattr(mod, "check_interface_field_types", lambda *a, **k: None)

    reset_enum_registry()
    reg = get_enum_registry()
    reg.register_enum("AnimSetKeys", {"StageA": 1}, source="AutoKeys", require_pascal_case_items=False)

    ws = _build_min_sheet("Enemy")
    _set_row(ws, 3, ["", "int", "enum(AnimSetKeys)"])
    _set_row(ws, 4, ["", "", "optional"])
    _set_row(ws, 7, ["", 1, None])

    data = WorksheetData(ws)
    props = data._get_properties_dict()
    assert props["value"] == "AnimSetKeys?"

    data.generate_json(str(tmp_path))
    out_file = tmp_path / "EnemyConfig.json"
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert content["1"]["value"] is None
