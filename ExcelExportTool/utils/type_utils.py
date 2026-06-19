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
TYPE_CALL_RE = re.compile(r"^([A-Za-z_]\w*)\s*\((.*)\)$", re.DOTALL)

CONSTRAINED_SCALAR_TYPE_RULES = {
    "nnint": ("int", "nonnegative"),
    "nnfloat": ("float", "nonnegative"),
    "pint": ("int", "positive"),
    "pfloat": ("float", "positive"),
}

SCALAR_TYPE_ALIASES = {
    "int": "int",
    "int32": "int",
    "integer": "int",
    "float": "float",
    "double": "float",
    "str": "string",
    "string": "string",
    "bool": "bool",
    "boolean": "bool",
    **{name: base for name, (base, _) in CONSTRAINED_SCALAR_TYPE_RULES.items()},
}

NONNEGATIVE_INT_TYPE_NAMES = {
    name for name, (base, rule) in CONSTRAINED_SCALAR_TYPE_RULES.items()
    if base == "int" and rule == "nonnegative"
}
NONNEGATIVE_FLOAT_TYPE_NAMES = {
    name for name, (base, rule) in CONSTRAINED_SCALAR_TYPE_RULES.items()
    if base == "float" and rule == "nonnegative"
}
POSITIVE_INT_TYPE_NAMES = {
    name for name, (base, rule) in CONSTRAINED_SCALAR_TYPE_RULES.items()
    if base == "int" and rule == "positive"
}
POSITIVE_FLOAT_TYPE_NAMES = {
    name for name, (base, rule) in CONSTRAINED_SCALAR_TYPE_RULES.items()
    if base == "float" and rule == "positive"
}
UNILIST_TYPE_NAMES = {"unilist"}

TYPE_ALIASES = {
    "i18n": "Localization.LocalizedStringRef",
}


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


def resolve_type_alias(type_str: str) -> str:
    """展开内置类型别名，保留原类型约束块。"""
    raw = (type_str or "").strip()
    if not raw:
        return raw

    raw, constraint = _split_type_constraints(raw)

    resolved = _resolve_type_alias_inner(raw)
    return f"{resolved}{constraint}"


def _resolve_type_alias_inner(type_str: str) -> str:
    return _normalize_type_expr(type_str, normalize_short_scalars=False)


def normalize_type_annotation(type_str: str) -> str:
    """递归规范化类型注解，将短名基础类型转为运行时/C#基础类型。"""
    raw = (type_str or "").strip()
    if not raw:
        return raw

    raw, constraint = _split_type_constraints(raw)
    normalized = _normalize_type_expr(raw, normalize_short_scalars=True)
    return f"{normalized}{constraint}"


def _split_type_constraints(type_str: str) -> tuple[str, str]:
    m = _CONSTRAINT_BLOCK_RE.match(type_str.strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return type_str.strip(), ""


def _normalize_type_expr(type_str: str, normalize_short_scalars: bool) -> str:
    t = (type_str or "").strip()
    if not t:
        return t

    lowered = t.lower()
    alias = TYPE_ALIASES.get(lowered)
    if alias:
        return alias

    if normalize_short_scalars:
        scalar_alias = SCALAR_TYPE_ALIASES.get(lowered)
        if scalar_alias:
            return scalar_alias

    call_match = TYPE_CALL_RE.match(t)
    if not call_match:
        return t

    container = call_match.group(1).lower()
    args = call_match.group(2).strip()

    if container in ("list", "unilist"):
        inner = _normalize_type_expr(args, normalize_short_scalars)
        return f"{container}({inner})"

    if container == "dict":
        parts = split_type_arguments(args)
        if len(parts) != 2:
            return t
        key_type = _normalize_type_expr(parts[0], normalize_short_scalars)
        value_type = _normalize_type_expr(parts[1], normalize_short_scalars)
        return f"dict({key_type},{value_type})"

    if container == "enum":
        return f"enum({args})"

    return t


def split_type_arguments(args: str) -> list[str]:
    """按顶层逗号拆分类型参数，忽略嵌套括号内的逗号。"""
    result: list[str] = []
    current: list[str] = []
    depth = 0
    for char in args:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        result.append("".join(current).strip())
    return result


def parse_type_annotation(type_str: str) -> Tuple[str, Optional[str]]:
    """
    解析类型注解（自动剥离末尾约束块 ``{...}``）。

    Returns:
        (类型种类, 基础类型或枚举名)
        类型种类: "scalar", "list", "dict", "enum", "unilist"
    """
    t = strip_type_constraints(normalize_type_annotation((type_str or "").strip()))

    def base_norm(s: str) -> str:
        raw = s.strip()
        return SCALAR_TYPE_ALIASES.get(raw.lower(), raw)

    # 检查是否是 enum(枚举名)
    enum_match = ENUM_TYPE_RE.match(t)
    if enum_match:
        enum_name = enum_match.group(1).strip()
        return "enum", enum_name

    # 检查是否是 unilist(...)（需要唯一性检查的列表）
    unilist_match = re.match(r"^unilist\s*\(\s*(.+)\s*\)$", t, re.IGNORECASE)
    if unilist_match:
        inner = unilist_match.group(1).strip()
        inner_enum_match = ENUM_TYPE_RE.match(inner)
        if inner_enum_match:
            enum_name = inner_enum_match.group(1).strip()
            return "unilist", f"enum({enum_name})"
        return "unilist", base_norm(inner)

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
    Supports: list, unilist, dict, enum(EnumName)
    """
    normalized = strip_type_constraints(normalize_type_annotation((type_str or "").strip()))
    return _convert_type_expr_to_csharp(normalized)


def _convert_type_expr_to_csharp(type_str: str) -> str:
    t = (type_str or "").strip()
    if not t:
        return t

    scalar = SCALAR_TYPE_ALIASES.get(t.lower())
    if scalar:
        return scalar

    call_match = TYPE_CALL_RE.match(t)
    if not call_match:
        return t

    container = call_match.group(1).lower()
    args = call_match.group(2).strip()

    if container == "enum":
        return args

    if container in ("list", "unilist"):
        return f"List<{_convert_type_expr_to_csharp(args)}>"

    if container == "dict":
        parts = split_type_arguments(args)
        if len(parts) != 2:
            return t
        key_cs = _convert_type_expr_to_csharp(parts[0])
        value_cs = _convert_type_expr_to_csharp(parts[1])
        return f"Dictionary<{key_cs},{value_cs}>"

    return t
