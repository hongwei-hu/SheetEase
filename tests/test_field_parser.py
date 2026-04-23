"""字段前缀解析测试。"""

from ExcelExportTool.parsing.field_parser import (
    parse_ref_prefix,
    parse_asset_prefix,
    get_field_tags,
    parse_key_prefix,
    extract_actual_field_name,
    value_type_ok,
)


def test_parse_ref_prefix_and_actual_name():
    assert parse_ref_prefix("[Item/id]itemRef") == ("Item", "id")
    assert parse_ref_prefix("[Item]itemRef") == ("Item", None)
    assert extract_actual_field_name("[Item/id]itemRef") == "itemRef"


def test_parse_asset_prefix_and_tags():
    assert parse_asset_prefix("[Asset]icon") == ("icon", None)
    assert parse_asset_prefix("[Asset:png]icon") == ("icon", "png")
    assert get_field_tags("[Asset]icon") == ["asset"]
    assert get_field_tags("[Asset:png]icon") == ["asset:png"]


def test_parse_key_prefix_and_actual_name():
    assert parse_key_prefix("key1:groupId") == ("key1", "groupId")
    assert parse_key_prefix("key2:subId") == ("key2", "subId")
    assert extract_actual_field_name("key1:groupId") == "groupId"
    assert extract_actual_field_name("key2:subId") == "subId"


def test_value_type_ok_basic():
    assert value_type_ok("int", 1)
    assert not value_type_ok("int", True)
    assert value_type_ok("float", 1.5)
    assert value_type_ok("float", 1)
    assert not value_type_ok("float", True)
    assert value_type_ok("string", "x")
    assert value_type_ok("bool", False)
