# Author: huhongwei 306463233@qq.com
# Created: 2024-09-10
# MIT License
# All rights reserved

import re
from typing import Any, Callable, Dict, List, Optional
from .exceptions import UnknownCustomTypeError, CustomTypeParseError
from .log import log_warn
from .naming_utils import is_valid_csharp_identifier
from .type_utils import parse_type_annotation
import re


# Compatibility alias
def available_csharp_enum_name(name: str) -> bool:
    return is_valid_csharp_identifier(name)

# 基本类型映射
def _parse_bool(x):
    if x is None or (isinstance(x, str) and x.strip() == ""):
        return False
    s = str(x).strip().lower()
    if s in ("1", "true"): return True
    if s in ("0", "false"): return False
    # 其它非法值，仍返回False，但后续会警告
    return False

PRIMITIVE_TYPE_MAPPING: Dict[str, Callable[[Any], Any]] = {
    "int": int,
    "float": float,
    "bool": _parse_bool,
    "str": str,
    "string": str,  # 兼容别名
}

# ================= 自定义类型注册机制 =================
class _CustomTypeHandler:
    def __init__(self, parser: Callable[[Optional[str]], Any]):
        self.parser = parser

class CustomTypeRegistry:
    def __init__(self):
        self._handlers: Dict[str, _CustomTypeHandler] = {}

    def register(self, full_name: str, parser: Callable[[Optional[str]], Any]):
        self._handlers[full_name] = _CustomTypeHandler(parser)

    def parse(self, full_name: str, raw: Any, field: str | None = None, sheet: str | None = None):
        h = self._handlers.get(full_name)
        if not h:
            raise UnknownCustomTypeError(full_name, field, sheet)
        try:
            return h.parser(None if raw is None else str(raw))
        except Exception as e:
            raise CustomTypeParseError(full_name, str(raw), str(e), field, sheet)

    def contains(self, full_name: str) -> bool:
        return full_name in self._handlers

    def all_types(self):
        return list(self._handlers.keys())

custom_type_registry = CustomTypeRegistry()

# 是否启用未注册自定义类型的通用回退解析
GENERIC_CUSTOM_TYPE_FALLBACK = True

def _generic_custom_type_object(full_name: str, raw: Optional[str]):
    """通用自定义类型打包：按 '#' 切分为 segments，保留原串。
    JSON 结构: {"__type": full_name, "__raw": original, "segments": [..]}
    空值 -> {"__type": full_name, "segments": []}
    """
    if raw is None or raw == "":
        return {"__type": full_name, "segments": []}
    txt = raw.replace("\r\n", "\n")
    parts = [p.strip() for p in txt.split('#')]
    return {"__type": full_name, "__raw": txt, "segments": parts}

def _parse_localized_string_ref(raw: Optional[str]):
    """默认示例: Localization.LocalizedStringRef 形如 文本#上下文 (#可省)."""
    if raw is None or raw == "":
        return {"keyHash": 0, "source": "", "context": ""}
    txt = raw.replace("\r\n", "\n")
    if "#" in txt:
        src, ctx = txt.split("#", 1)
    else:
        src, ctx = txt, ""
    src = src.strip(); ctx = ctx.strip()
    return {"keyHash": 0, "source": src, "context": ctx}

# 注册示例（可通过外部扩展继续添加）
custom_type_registry.register("Localization.LocalizedStringRef", _parse_localized_string_ref)
# =====================================================


def available_csharp_enum_name(name: str) -> bool:
    """检查是否为合法的C#枚举名"""
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(name)))


def convert_to_type(type_str: str, value: Any, field: str | None = None, sheet: str | None = None, row: int | None = None, col: int | None = None) -> Any:
    """根据类型字符串转换值 (支持基础/list/dict/自定义全限定类型)"""
    if not type_str:
        raise ValueError("空类型定义")
    type_str = type_str.strip()

    # 基础
    if type_str in PRIMITIVE_TYPE_MAPPING:
        return _convert_primitive(type_str, value, field, sheet, row, col)
    # 容器
    if type_str.startswith("dict"):
        return _convert_dict(type_str, value, field, sheet, row, col)
    if type_str.startswith("list"):
        return _convert_list(type_str, value, field, sheet, row, col)
    # 自定义(简单策略: 至少包含一个 . 视为全限定类型)
    if "." in type_str:
        if custom_type_registry.contains(type_str):
            return custom_type_registry.parse(type_str, value, field, sheet)
        if GENERIC_CUSTOM_TYPE_FALLBACK:
            return _generic_custom_type_object(type_str, None if value is None else str(value))
        # 未开启通用回退仍旧报错
        raise UnknownCustomTypeError(type_str, field, sheet)
    raise ValueError(f"Unsupported data type: {type_str}")


def _convert_primitive(type_str: str, value: Any, field: str = None, sheet: str = None, row: int = None, col: int = None) -> Any:
    """转换为基本类型，并做C#风格范围/合法性检查"""
    converter = PRIMITIVE_TYPE_MAPPING[type_str]
    if value is None:
        v = "" if type_str in ("str", "string") else converter(0)
        _check_csharp_primitive_range(type_str, v, raw=value, field=field, sheet=sheet, row=row, col=col)
        return v
    v = converter(value)
    _check_csharp_primitive_range(type_str, v, raw=value, field=field, sheet=sheet, row=row, col=col)
    return v


def _check_csharp_primitive_range(type_str: str, v: Any, raw: Any = None, field: str = None, sheet: str = None, row: int = None, col: int = None):
    """对C#基础类型做范围/合法性检查，超出范围时抛出异常，支持表名/行/列定位"""
    prefix = f"[{sheet}] " if sheet else ""
    if row is not None:
        prefix += f"行{row} "
    if col is not None:
        prefix += f"列{col} "
    if field:
        prefix += f"字段{field} "
    # int: [-2^31, 2^31-1]
    if type_str == "int":
        try:
            ival = int(v)
            if ival < -2147483648 or ival > 2147483647:
                raise ValueError(f"{prefix}值{raw!r}超出C# int范围[-2147483648,2147483647]，实际为{ival}")
        except Exception:
            raise ValueError(f"{prefix}值{raw!r}无法转换为C# int")
    # float: [-3.4028235e38, 3.4028235e38]
    elif type_str == "float":
        try:
            fval = float(v)
            if abs(fval) > 3.4028235e38:
                raise ValueError(f"{prefix}值{raw!r}超出C# float范围[-3.4028235e38,3.4028235e38]，实际为{fval}")
        except Exception:
            raise ValueError(f"{prefix}值{raw!r}无法转换为C# float")
    # bool: 仅允许true/false/1/0，空值(None/"")视为False且不警告
    elif type_str == "bool":
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            return  # 空值不警告
        sval = str(raw).strip().lower()
        if sval not in ("1", "0", "true", "false"):
            raise ValueError(f"{prefix}值{raw!r}不是C# bool允许的取值(true/false/1/0)")
    # string: 警告超长
    elif type_str in ("str", "string"):
        if isinstance(v, str) and len(v) > 65535:
            raise ValueError(f"{prefix}字符串长度{len(v)}超出C# string推荐上限65535，可能导致序列化或存储异常")


def _convert_dict(type_str: str, value: Any, field: str = None, sheet: str = None, row: int = None, col: int = None) -> Dict[Any, Any]:
    """转换为字典类型，例如 dict(int,string)，并递归做C#范围检查"""
    result: Dict[Any, Any] = {}
    type_match = re.search(r"\((.*)\)", type_str)
    if not type_match or value is None:
        return result
    key_type_str, value_type_str = map(str.strip, type_match.group(1).split(","))
    # 支持嵌套类型
    for line in str(value).splitlines():
        if ":" in line:
            key, val = map(str.strip, line.split(":", 1))
            # key 只支持基础类型
            key_conv = PRIMITIVE_TYPE_MAPPING.get(key_type_str, str)
            k = key_conv(key)
            # value 支持递归
            v = _convert_with_check(value_type_str, val, field=field, sheet=sheet, row=row, col=col)
            result[k] = v
    return result


def _convert_list(type_str: str, value: Any, field: str = None, sheet: str = None, row: int = None, col: int = None) -> List[Any]:
    """转换为列表类型，例如 list(int)，并递归做C#范围检查"""
    result: List[Any] = []
    type_match = re.search(r"\((.*)\)", type_str)
    if not type_match or value is None:
        return result
    element_type_str = type_match.group(1).strip()
    # 支持递归
    if isinstance(value, str):
        for v in value.split(","):
            v = v.strip()
            if v:
                result.append(_convert_with_check(element_type_str, v, field=field, sheet=sheet, row=row, col=col))
        return result
    # 单元素
    try:
        result.append(_convert_with_check(element_type_str, value, field=field, sheet=sheet, row=row, col=col))
        return result
    except Exception as e:
        raise ValueError(f"无法将 {value} 转换为 {type_str}: {e}")


def _convert_with_check(type_str: str, value: Any, field: str = None, sheet: str = None, row: int = None, col: int = None):
    """递归类型转换+范围检查。支持基础、list、dict。"""
    type_str = type_str.strip()
    if type_str in PRIMITIVE_TYPE_MAPPING:
        v = PRIMITIVE_TYPE_MAPPING[type_str](value)
        _check_csharp_primitive_range(type_str, v, raw=value, field=field, sheet=sheet, row=row, col=col)
        return v
    if type_str.startswith("list"):
        return _convert_list(type_str, value, field=field, sheet=sheet, row=row, col=col)
    if type_str.startswith("dict"):
        return _convert_dict(type_str, value, field=field, sheet=sheet, row=row, col=col)
    # 其它类型暂不递归
    return value
