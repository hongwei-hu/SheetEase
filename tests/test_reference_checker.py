"""引用检查器测试。"""

import json

from ExcelExportTool.validation.reference_checker import ReferenceChecker


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def test_reference_checker_scalar_success_logs_info(tmp_path, monkeypatch):
    target = tmp_path / "ItemConfig.json"
    _write_json(target, {"1": {"id": 1, "name": "A"}})

    logs = {"info": [], "warn": [], "error": []}
    import ExcelExportTool.validation.reference_checker as mod
    monkeypatch.setattr(mod, "log_info", lambda m: logs["info"].append(m))
    monkeypatch.setattr(mod, "log_warn", lambda m: logs["warn"].append(m))
    monkeypatch.setattr(mod, "log_error", lambda m: logs["error"].append(m))

    checker = ReferenceChecker("Shop", "Shop.xlsx")
    checker.add_pending_check(
        {
            "excel_row": 7,
            "field_name": "itemId",
            "ref_sheet": "Item",
            "ref_field": "id",
            "kind": "scalar",
            "base": "int",
            "value": 1,
        }
    )
    checker.run_checks([str(tmp_path)], {"Item": "Item.xlsx"})

    assert not logs["warn"]
    assert not logs["error"]
    assert any("没有引用丢失" in m for m in logs["info"])


def test_reference_checker_missing_target_warns(tmp_path, monkeypatch):
    logs = {"warn": []}
    import ExcelExportTool.validation.reference_checker as mod
    monkeypatch.setattr(mod, "log_warn", lambda m: logs["warn"].append(m))

    checker = ReferenceChecker("Shop", "Shop.xlsx")
    checker.add_pending_check(
        {
            "excel_row": 8,
            "field_name": "itemId",
            "ref_sheet": "Missing",
            "ref_field": "id",
            "kind": "scalar",
            "base": "int",
            "value": 1,
        }
    )
    checker.run_checks([str(tmp_path)], {})

    assert any("未找到目标表 JSON" in m for m in logs["warn"])


def test_reference_checker_type_mismatch_and_empty_whitelist(tmp_path, monkeypatch):
    target = tmp_path / "ItemConfig.json"
    _write_json(target, {"1": {"id": 1, "name": "A"}})

    logs = {"error": []}
    import ExcelExportTool.validation.reference_checker as mod
    monkeypatch.setattr(mod, "log_error", lambda m: logs["error"].append(m))
    monkeypatch.setattr(mod, "log_warn", lambda m: None)
    monkeypatch.setattr(mod, "log_info", lambda m: None)

    checker = ReferenceChecker("Shop", "Shop.xlsx")
    checker.add_pending_check(
        {
            "excel_row": 9,
            "field_name": "itemId",
            "ref_sheet": "Item",
            "ref_field": "id",
            "kind": "scalar",
            "base": "string",
            "value": "1",
        }
    )
    # int 引用值 0 应视为空引用并跳过，不产生不存在错误
    checker.add_pending_check(
        {
            "excel_row": 10,
            "field_name": "optionalItemId",
            "ref_sheet": "Item",
            "ref_field": "id",
            "kind": "scalar",
            "base": "int",
            "value": 0,
        }
    )
    checker.run_checks([str(tmp_path)], {"Item": "Item.xlsx"})

    assert any("引用类型不匹配" in m for m in logs["error"])
    assert not any("optionalItemId" in m and "不存在" in m for m in logs["error"])


def test_reference_checker_run_checks_is_idempotent(tmp_path, monkeypatch):
    target = tmp_path / "ItemConfig.json"
    _write_json(target, {"1": {"id": 1}})

    logs = {"info": 0}
    import ExcelExportTool.validation.reference_checker as mod
    monkeypatch.setattr(mod, "log_info", lambda m: logs.__setitem__("info", logs["info"] + 1))
    monkeypatch.setattr(mod, "log_warn", lambda m: None)
    monkeypatch.setattr(mod, "log_error", lambda m: None)

    checker = ReferenceChecker("Shop", "Shop.xlsx")
    checker.add_pending_check(
        {
            "excel_row": 7,
            "field_name": "itemId",
            "ref_sheet": "Item",
            "ref_field": "id",
            "kind": "scalar",
            "base": "int",
            "value": 1,
        }
    )
    checker.run_checks([str(tmp_path)], {"Item": "Item.xlsx"})
    checker.run_checks([str(tmp_path)], {"Item": "Item.xlsx"})

    assert logs["info"] == 1
