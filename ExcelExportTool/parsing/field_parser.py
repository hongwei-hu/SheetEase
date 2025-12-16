# Author: huhongwei 306463233@qq.com
# MIT License
"""
字段名解析模块：处理字段名前缀解析（key1:, key2:, [Sheet/Field], [Asset]等）。
"""
import re
from typing import Optional, Tuple


# 字段名前缀正则表达式
KEY1_PREFIX_RE = re.compile(r"^\s*key1\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
KEY2_PREFIX_RE = re.compile(r"^\s*key2\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
# [Sheet/Field]FieldName 或 [Sheet]FieldName（省略 Field -> 默认 id）
# 引用标记：[Sheet/Field]FieldName（Sheet 名不允许包含 ':'，避免与 [Asset:ext] 混淆）
REF_PREFIX_RE = re.compile(r"^\s*\[(?P<sheet>[^:/\]]+)(?:/(?P<field>[^\]]+))?\]\s*(?P<name>.+)$")
# [Asset]FieldName 或 [Asset:png]FieldName —— 资源文件校验标记
ASSET_PREFIX_RE = re.compile(r"^\s*\[(?:asset)(?::(?P<ext>[A-Za-z0-9_]+))?\]\s*(?P<name>.+)$", re.IGNORECASE)


# parse_type_annotation 已移至 type_utils.py 以支持枚举类型
# 这里重新导出以保持向后兼容
from ..utils.type_utils import parse_type_annotation


def value_type_ok(base: str, v: any) -> bool:
    """检查值是否符合指定的基础类型"""
    if v is None:
        return False
    if base == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if base == "float":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if base == "string":
        return isinstance(v, str)
    if base == "bool":
        return isinstance(v, bool)
    # 未知类型：不强校验
    return True


def extract_actual_field_name(raw_field_name: str) -> str:
    """
    从原始字段名中提取真实字段名（去掉所有前缀）。
    
    Args:
        raw_field_name: 原始字段名，可能包含 key1:, key2:, [Sheet/Field], [Asset] 等前缀
        
    Returns:
        去掉前缀后的真实字段名
    """
    if not isinstance(raw_field_name, str):
        return str(raw_field_name)
    
    # 检查 key1: 前缀
    m1 = KEY1_PREFIX_RE.match(raw_field_name)
    if m1:
        return m1.group("name").strip()
    
    # 检查 key2: 前缀
    m2 = KEY2_PREFIX_RE.match(raw_field_name)
    if m2:
        return m2.group("name").strip()
    
    # 去掉资源前缀 [Asset] / [Asset:ext]
    m_asset = ASSET_PREFIX_RE.match(raw_field_name)
    if m_asset:
        return m_asset.group("name").strip()
    
    # 去掉引用前缀 [Sheet/Field]
    m3 = REF_PREFIX_RE.match(raw_field_name)
    if m3:
        return m3.group("name").strip()
    
    return raw_field_name


def parse_ref_prefix(raw_field_name: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    解析引用前缀 [Sheet/Field] 或 [Sheet]。
    
    Returns:
        (sheet_name, field_name) 或 None（如果不是引用标记）
    """
    if not isinstance(raw_field_name, str):
        return None
    m = REF_PREFIX_RE.match(raw_field_name)
    if m:
        sheet = m.group("sheet").strip()
        field = m.group("field")
        field = field.strip() if field else None
        return (sheet, field)
    return None


def parse_asset_prefix(raw_field_name: str) -> Optional[Tuple[str, Optional[str]]]:
    """
    解析资源前缀 [Asset] 或 [Asset:ext]。
    
    Returns:
        (field_name, ext) 或 None（如果不是资源标记）
    """
    if not isinstance(raw_field_name, str):
        return None
    m = ASSET_PREFIX_RE.match(raw_field_name)
    if m:
        ext = m.group("ext")
        field_name = m.group("name").strip()
        ext = ext.strip().lower() if isinstance(ext, str) and ext.strip() else None
        return (field_name, ext)
    return None


def parse_key_prefix(raw_field_name: str) -> Optional[Tuple[str, str]]:
    """
    解析 key1: 或 key2: 前缀。
    
    Returns:
        ("key1" 或 "key2", real_field_name) 或 None（如果不是 key 前缀）
    """
    if not isinstance(raw_field_name, str):
        return None
    
    m1 = KEY1_PREFIX_RE.match(raw_field_name)
    if m1:
        return ("key1", m1.group("name").strip())
    
    m2 = KEY2_PREFIX_RE.match(raw_field_name)
    if m2:
        return ("key2", m2.group("name").strip())
    
    return None

