"""枚举注册表测试。"""

import pytest

from ExcelExportTool.generation.enum_registry import EnumRegistry, reset_enum_registry, get_enum_registry
from ExcelExportTool.exceptions import ExportError


def test_register_and_query_enum():
    reg = EnumRegistry()
    reg.register_enum("QualityType", {"Common": 0, "Rare": 1}, source="A.xlsx")
    assert reg.has_enum("QualityType")
    assert reg.get_enum_value("QualityType", "Rare") == 1
    assert reg.validate_enum_item("QualityType", "Common")


def test_register_duplicate_enum_raises():
    reg = EnumRegistry()
    reg.register_enum("QualityType", {"Common": 0}, source="A.xlsx")
    with pytest.raises(ExportError, match="重复定义"):
        reg.register_enum("QualityType", {"Common": 0}, source="B.xlsx")


def test_register_duplicate_with_different_items_raises():
    reg = EnumRegistry()
    reg.register_enum("QualityType", {"Common": 0}, source="A.xlsx")
    with pytest.raises(ExportError, match="枚举项不一致"):
        reg.register_enum("QualityType", {"Rare": 1}, source="B.xlsx")


def test_get_missing_enum_value_raises():
    reg = EnumRegistry()
    reg.register_enum("QualityType", {"Common": 0}, source="A.xlsx")
    with pytest.raises(ExportError, match="不存在枚举项"):
        reg.get_enum_value("QualityType", "Rare")


def test_global_registry_reset():
    reset_enum_registry()
    reg = get_enum_registry()
    reg.register_enum("TmpEnum", {"A": 0}, source="T.xlsx")
    assert reg.has_enum("TmpEnum")
    reset_enum_registry()
    reg2 = get_enum_registry()
    assert not reg2.has_enum("TmpEnum")


def test_relaxed_enum_item_name_validation_for_auto_keys():
    reg = EnumRegistry()
    reg.register_enum(
        "CombatAttributeKeys",
        {"current_hp": 0},
        source="AutoKeys",
        require_pascal_case_items=False,
    )
    assert reg.enum_requires_pascal_case_items("CombatAttributeKeys") is False
    assert reg.validate_enum_item_name("current_hp", require_pascal_case=False)


def test_strict_enum_item_name_validation_for_manual_enum():
    reg = EnumRegistry()
    reg.register_enum("QualityType", {"Common": 0}, source="EnumSheet")
    assert reg.enum_requires_pascal_case_items("QualityType") is True
    assert not reg.validate_enum_item_name("common", require_pascal_case=True)
