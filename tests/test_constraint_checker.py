"""单元测试：约束解析与约束检查模块。"""

from ExcelExportTool.validation.constraint_checker import (
    split_type_and_constraint_str,
    parse_constraint_str,
    check_constraints,
)


def test_split_type_and_constraint_str():
    assert split_type_and_constraint_str("int{min:0,max:100}") == ("int", "min:0,max:100")
    assert split_type_and_constraint_str("list(int){nonempty,unique}") == ("list(int)", "nonempty,unique")
    assert split_type_and_constraint_str("string") == ("string", "")


def test_parse_constraint_str_with_numbers_and_flags_and_pattern():
    parsed = parse_constraint_str('min:1, max:5, nonempty, pattern:"^a,b$"')
    assert parsed["min"] == 1
    assert parsed["max"] == 5
    assert parsed["nonempty"] is True
    assert parsed["pattern"] == "^a,b$"


def test_check_constraints_numeric_rules():
    constraints = parse_constraint_str("min:1,max:5,nonzero")
    assert check_constraints(3, constraints, "scalar", "int", "lv", "Item", 7) == []

    violations = check_constraints(0, constraints, "scalar", "int", "lv", "Item", 7)
    assert any("不能为 0" in v for v in violations)

    violations = check_constraints(6, constraints, "scalar", "int", "lv", "Item", 7)
    assert any("大于最大值" in v for v in violations)


def test_check_constraints_string_rules():
    constraints = parse_constraint_str('nonempty,minlen:2,maxlen:5,pattern:"^[A-Z]+$"')
    assert check_constraints("AB", constraints, "scalar", "string", "code", "Item", 8) == []

    violations = check_constraints("", constraints, "scalar", "string", "code", "Item", 8)
    assert any("不能为空" in v for v in violations)

    violations = check_constraints("ABCDEF", constraints, "scalar", "string", "code", "Item", 8)
    assert any("超过最大长度" in v for v in violations)

    violations = check_constraints("Ab", constraints, "scalar", "string", "code", "Item", 8)
    assert any("不匹配格式" in v for v in violations)


def test_check_constraints_list_rules():
    constraints = parse_constraint_str("nonempty,minlen:2,maxlen:3,unique")
    assert check_constraints([1, 2], constraints, "list", "int", "ids", "Item", 9) == []

    violations = check_constraints([], constraints, "list", "int", "ids", "Item", 9)
    assert any("列表不能为空" in v for v in violations)

    violations = check_constraints([1, 1], constraints, "list", "int", "ids", "Item", 9)
    assert any("重复元素" in v for v in violations)


def test_check_constraints_dict_rules():
    constraints = parse_constraint_str("nonempty,minsize:1,maxsize:2")
    assert check_constraints({"a": 1}, constraints, "dict", "int", "map", "Item", 10) == []

    violations = check_constraints({}, constraints, "dict", "int", "map", "Item", 10)
    assert any("字典不能为空" in v for v in violations)

    violations = check_constraints({"a": 1, "b": 2, "c": 3}, constraints, "dict", "int", "map", "Item", 10)
    assert any("超过最大值" in v for v in violations)
