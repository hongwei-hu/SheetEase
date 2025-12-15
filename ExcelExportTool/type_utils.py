"""Type utilities: parse annotations and convert to C# type strings.

Extracted from worksheet_data and cs_generation to centralize type logic.
"""
from typing import Tuple, Optional
import re


def parse_type_annotation(type_str: str) -> Tuple[str, Optional[str]]:
    """
    解析类型注解
    
    Returns:
        (类型种类, 基础类型或枚举名)
        类型种类: "scalar", "list", "dict", "enum"
    """
    t = (type_str or "").strip()

    def base_norm(s: str) -> str:
        s = s.strip().lower()
        if s in ("int", "int32", "integer"): return "int"
        if s in ("float", "double"): return "float"
        if s in ("str", "string"): return "string"
        if s in ("bool", "boolean"): return "bool"
        return s

    # 检查是否是 enum(枚举名)
    enum_match = re.match(r"^enum\s*\(\s*([^)]+)\s*\)$", t, re.IGNORECASE)
    if enum_match:
        enum_name = enum_match.group(1).strip()
        return "enum", enum_name

    # 检查是否是 list(enum(枚举名))
    list_match = re.match(r"^list\s*\(\s*(.+)\s*\)$", t, re.IGNORECASE)
    if list_match:
        inner = list_match.group(1).strip()
        inner_enum_match = re.match(r"^enum\s*\(\s*([^)]+)\s*\)$", inner, re.IGNORECASE)
        if inner_enum_match:
            enum_name = inner_enum_match.group(1).strip()
            return "list", f"enum({enum_name})"
        return "list", base_norm(inner)
    
    # 检查是否是 dict(..., enum(枚举名))
    dict_match = re.match(r"^dict\s*\(\s*([^,]+)\s*,\s*(.+)\s*\)$", t, re.IGNORECASE)
    if dict_match:
        key_type = dict_match.group(1).strip()
        value_type = dict_match.group(2).strip()
        value_enum_match = re.match(r"^enum\s*\(\s*([^)]+)\s*\)$", value_type, re.IGNORECASE)
        if value_enum_match:
            enum_name = value_enum_match.group(1).strip()
            return "dict", f"enum({enum_name})"
        return "dict", None
    
    return "scalar", base_norm(t)


def convert_type_to_csharp(type_str: str) -> str:
    """
    Convert a type annotation to C# representation.
    Supports: list, dict, enum(EnumName)
    """
    import re
    
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
