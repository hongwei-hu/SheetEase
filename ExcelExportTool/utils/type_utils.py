"""Type utilities: parse annotations and convert to C# type strings.

Extracted from worksheet_data and cs_generation to centralize type logic.
"""
from typing import Tuple, Optional
import re
from ..exceptions import ExportError

# 约束块正则：匹配末尾的 {...}（不含嵌套花括号）
_CONSTRAINT_BLOCK_RE = re.compile(r'^(.*?)(\{[^{}]*\})\s*$', re.DOTALL)
ENUM_TYPE_RE = re.compile(r"^enum\s*\(\s*([^)]+)\s*\)$", re.IGNORECASE)
LIST_TYPE_RE = re.compile(r"^list\s*\(\s*(.+)\s*\)$", re.IGNORECASE)
DICT_TYPE_RE = re.compile(r"^dict\s*\(\s*([^,]+)\s*,\s*(.+)\s*\)$", re.IGNORECASE)

NONNEGATIVE_INT_TYPE_NAMES = {"nnint"}
NONNEGATIVE_FLOAT_TYPE_NAMES = {"nnfloat"}
POSITIVE_INT_TYPE_NAMES = {"pint"}
POSITIVE_FLOAT_TYPE_NAMES = {"pfloat"}


def strip_type_constraints(type_str: str) -> str:
    """
    从类型注解字符串中剥离末尾的约束块 ``{...}``。

    Examples:
        ``"int{min:0, max:100}"`` -> ``"int"``
        ``"list(int){nonempty}"`` -> ``"list(int)"``
        ``"string"``              -> ``"string"``
    """
    if not type_str or '{' not in type_str:
        return (type_str or "").strip()
    m = _CONSTRAINT_BLOCK_RE.match(type_str.strip())
    return m.group(1).strip() if m else type_str.strip()


def parse_type_annotation(type_str: str) -> Tuple[str, Optional[str]]:
    """
    解析类型注解（自动剥离末尾约束块 ``{...}``）。

    Returns:
        (类型种类, 基础类型或枚举名)
        类型种类: "scalar", "list", "dict", "enum"
    """
    t = strip_type_constraints((type_str or "").strip())

    def base_norm(s: str) -> str:
        s = s.strip().lower()
        if s in ("int", "int32", "integer"): return "int"
        if s in ("float", "double"): return "float"
        if s in NONNEGATIVE_INT_TYPE_NAMES: return "int"
        if s in NONNEGATIVE_FLOAT_TYPE_NAMES: return "float"
        if s in POSITIVE_INT_TYPE_NAMES: return "int"
        if s in POSITIVE_FLOAT_TYPE_NAMES: return "float"
        if s in ("str", "string"): return "string"
        if s in ("bool", "boolean"): return "bool"
        return s

    # 检查是否是 enum(枚举名)
    enum_match = ENUM_TYPE_RE.match(t)
    if enum_match:
        enum_name = enum_match.group(1).strip()
        return "enum", enum_name

    # 检查是否是 list(enum(枚举名))
    list_match = LIST_TYPE_RE.match(t)
    if list_match:
        inner = list_match.group(1).strip()
        inner_enum_match = ENUM_TYPE_RE.match(inner)
        if inner_enum_match:
            enum_name = inner_enum_match.group(1).strip()
            return "list", f"enum({enum_name})"
        return "list", base_norm(inner)
    
    # 检查是否是 dict(..., enum(枚举名))
    dict_match = DICT_TYPE_RE.match(t)
    if dict_match:
        value_type = dict_match.group(2).strip()
        value_enum_match = ENUM_TYPE_RE.match(value_type)
        if value_enum_match:
            enum_name = value_enum_match.group(1).strip()
            return "dict", f"enum({enum_name})"
        return "dict", None
    
    return "scalar", base_norm(t)


def validate_type_annotation(type_str: str) -> Tuple[bool, str]:
    """
    验证类型注解的合法性（自动忽略末尾约束块 ``{...}``）。

    Args:
        type_str: 类型注解字符串

    Returns:
        (是否合法, 错误消息)
    """
    if not type_str or not isinstance(type_str, str):
        return False, "类型注解为空或不是字符串"

    type_str = strip_type_constraints(type_str.strip())
    if not type_str:
        return False, "类型注解为空"
    
    # 检查括号匹配
    if type_str.count('(') != type_str.count(')'):
        return False, "括号不匹配"
    
    # 检查嵌套深度（防止过深）
    depth = 0
    max_depth = 0
    for char in type_str:
        if char == '(':
            depth += 1
            max_depth = max(max_depth, depth)
        elif char == ')':
            depth -= 1
        if depth < 0:
            return False, "括号顺序错误"
    
    if max_depth > 3:  # 限制嵌套深度
        return False, f"嵌套深度过深: {max_depth} (最大允许3层)"
    
    # 检查基本格式：不能有连续的逗号、不能以逗号开头/结尾
    if type_str.startswith(',') or type_str.endswith(','):
        return False, "类型注解不能以逗号开头或结尾"
    
    if ',,' in type_str:
        return False, "类型注解不能包含连续的逗号"
    
    return True, ""


def convert_type_to_csharp(type_str: str) -> str:
    """
    Convert a type annotation to C# representation.
    Supports: list, dict, enum(EnumName)
    """
    import re
    type_str = strip_type_constraints((type_str or "").strip())
    
    normalized_scalar = parse_type_annotation(type_str)
    if normalized_scalar[0] == "scalar" and normalized_scalar[1] in ("int", "float", "string", "bool"):
        return normalized_scalar[1]

    # 处理 enum(枚举名)
    enum_match = re.match(r"^enum\s*\(\s*([^)]+)\s*\)$", type_str, re.IGNORECASE)
    if enum_match:
        enum_name = enum_match.group(1).strip()
        return enum_name  # 直接返回枚举类型名
    
    # 处理 list(enum(枚举名))
    list_enum_match = re.match(r"^list\s*\(\s*enum\s*\(\s*([^)]+)\s*\)\s*\)$", type_str, re.IGNORECASE)
    if list_enum_match:
        enum_name = list_enum_match.group(1).strip()
        return f"List<{enum_name}>"
    
    # 处理 dict(..., enum(枚举名))
    dict_enum_match = re.match(r"^dict\s*\(\s*([^,]+)\s*,\s*enum\s*\(\s*([^)]+)\s*\)\s*\)$", type_str, re.IGNORECASE)
    if dict_enum_match:
        key_type = dict_enum_match.group(1).strip()
        enum_name = dict_enum_match.group(2).strip()
        # 转换key类型
        key_cs = convert_type_to_csharp(key_type) if key_type not in ("int", "string", "float", "bool") else key_type
        return f"Dictionary<{key_cs}, {enum_name}>"
    
    # 原有的处理逻辑
    type_mappings = {"list": "List", "dict": "Dictionary"}
    for key, value in type_mappings.items():
        type_str = type_str.replace(key, value)
    return type_str.replace("(", "<").replace(")", ">")
