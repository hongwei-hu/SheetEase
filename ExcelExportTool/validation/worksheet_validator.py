# Author: huhongwei 306463233@qq.com
# MIT License
"""
工作表验证模块：提供各种验证和检查方法。
"""
import os
import re
from typing import Dict, Set
from collections import defaultdict

from ..parsing.data_processing import available_csharp_enum_name
from ..exceptions import InvalidEnumNameError, DuplicatePrimaryKeyError
from ..utils.log import log_warn
from ..utils.user_utils import user_confirm
from ..parsing.field_parser import value_type_ok
from ..utils.type_utils import parse_type_annotation


def check_hidden_and_merged(worksheet, sheet_name: str) -> None:
    """检测隐藏行/列与合并单元格，给出可能导致解析异常的提示。"""
    ws = worksheet
    # 隐藏行
    try:
        hidden_rows = [
            idx for idx, dim in ws.row_dimensions.items()
            if getattr(dim, 'hidden', False) or (hasattr(dim, 'height') and (dim.height == 0 or dim.height == 0.0))
        ]
    except Exception:
        hidden_rows = []
    if hidden_rows:
        sample = hidden_rows[:10]
        more = '' if len(hidden_rows) <= 10 else f" 等共{len(hidden_rows)}行"
        _msg = f"[{sheet_name}] 检测到隐藏行: {sample}{more}。隐藏行可能导致导出结果与期望不一致"
        log_warn(_msg, immediate=True)
        # 同时加入最终汇总
        log_warn(_msg, immediate=False)
    # 隐藏列（字母）
    try:
        hidden_cols = [
            col for col, dim in ws.column_dimensions.items()
            if getattr(dim, 'hidden', False) or (hasattr(dim, 'width') and (dim.width == 0 or dim.width == 0.0))
        ]
    except Exception:
        hidden_cols = []
    if hidden_cols:
        sample = hidden_cols[:10]
        more = '' if len(hidden_cols) <= 10 else f" 等共{len(hidden_cols)}列"
        _msg = f"[{sheet_name}] 检测到隐藏列: {sample}{more}。隐藏列可能导致导出结果与期望不一致"
        log_warn(_msg, immediate=True)
        log_warn(_msg, immediate=False)
    # 合并单元格
    try:
        merged_ranges = [str(r) for r in getattr(ws, 'merged_cells', None).ranges] if getattr(ws, 'merged_cells', None) else []
    except Exception:
        merged_ranges = []
    if merged_ranges:
        sample = merged_ranges[:5]
        more = '' if len(merged_ranges) <= 5 else f" 等共{len(merged_ranges)}处"
        _msg = f"[{sheet_name}] 检测到合并单元格: {sample}{more}。合并区域可能导致读取表头或数据对齐异常，建议取消合并"
        log_warn(_msg, immediate=True)
        log_warn(_msg, immediate=False)


def check_interface_field_types(sheet_name: str, properties_dict: Dict[str, str]) -> None:
    """
    自动解析 IConfigRawInfo.cs，获取接口字段及类型，对所有同名字段类型不符的都进行检查和提示。
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    interface_path = os.path.join(base_dir, "ProjectFolder", "ConfigData", "IConfigRawInfo.cs")
    if not os.path.exists(interface_path):
        # 在 PyInstaller 环境下尝试 _MEIPASS
        try:
            import sys
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                alt = os.path.join(meipass, "ProjectFolder", "ConfigData", "IConfigRawInfo.cs")
                if os.path.exists(alt):
                    interface_path = alt
        except Exception:
            pass
    # 若接口文件缺失，仍然对 id/name 使用内置期望（id:int, name:string）
    interface_missing = not os.path.exists(interface_path)
    content = ''
    if not interface_missing:
        with open(interface_path, encoding="utf-8") as f:
            content = f.read()
    # 匹配如 int id { get; } 或 string name { get; }
    pattern = re.compile(r"(int|string|float|double|bool)\s+(\w+)\s*{[^{]*?get;[^{]*?}")
    interface_fields = {m.group(2): m.group(1).lower() for m in pattern.finditer(content)} if content else {}
    if not interface_fields:
        # 没有在接口中解析到属性时，不中断；对 id/name 仍做内置期望检查
        pass
    props = properties_dict
    # 1) 对 id/name 执行强制一致性检查（必须与接口或内置期望一致），不通过则直接中断
    expected_id = (interface_fields.get('id') or 'int').lower()
    expected_name = (interface_fields.get('name') or 'string').lower()
    hard_errors: list[str] = []
    actual_id = props.get('id')
    if actual_id is not None and actual_id.lower() != expected_id:
        hard_errors.append(f"id 字段类型为 {actual_id}，必须为 {expected_id}，因为id属性必须跟接口一致。如果要保留类型{actual_id}，建议修改字段名")
    actual_name = props.get('name')
    if actual_name is not None and actual_name.lower() != expected_name:
        hard_errors.append(f"name 字段类型为 {actual_name}，必须为 {expected_name}，因为name属性必须跟接口一致。如果要保留类型{actual_name}，建议修改字段名")
    if hard_errors:
        detail = "\n".join(f"  - {x}" for x in hard_errors)
        raise RuntimeError(f"表[{sheet_name}] 字段类型错误：\n{detail}")

    # 2) 其他接口字段保持原有"提示并确认"的流程
    wrongs = []
    for fname, ftype in interface_fields.items():
        if fname in ('id', 'name'):
            continue  # 已做强制检查
        actual_type = props.get(fname)
        if actual_type is not None and actual_type.lower() != ftype:
            wrongs.append((fname, actual_type, ftype))
    if wrongs:
        msg = f"表[{sheet_name}] 字段类型警告：\n"
        for fname, actual, expect in wrongs:
            msg += f"  - {fname} 字段类型为 {actual}，应为 {expect}\n"
        msg += "这可能导致生成的 C# 脚本无法通过编译。\n是否继续导出？(y/n)"
        if user_confirm(msg):
            log_warn("用户选择继续导出")
        else:
            raise RuntimeError("用户取消导出：接口字段类型不符")


def validate_enum_name(name: str, excel_row: int) -> None:
    """检查枚举名是否合法（excel_row 为真实 Excel 行号，用于错误提示）"""
    if not available_csharp_enum_name(name):
        raise InvalidEnumNameError(name, excel_row)


def check_duplicate_enum_keys(row_data: list, sheet_name: str) -> None:
    """
    初始化时检查用于生成枚举的首列（字符串主键）：
    - 验证每个名字是否合法
    - 收集出现的 Excel 行号，若重复则抛错（显示真实 Excel 行号）
    """
    name_rows = defaultdict(list)
    for idx, row in enumerate(row_data):
        if not row:
            continue
        val = row[0].value
        excel_row = 7 + idx
        validate_enum_name(val, excel_row)
        name_rows[val].append(excel_row)
    dup = {k: v for k, v in name_rows.items() if len(v) > 1}
    if dup:
        lines = "; ".join(f"{k} -> 行{v}" for k, v in dup.items())
        raise InvalidEnumNameError(f"重复的字符串主键: {lines}", -1)


def check_duplicate_composite_keys(row_data: list, multiplier: int, max_key2: int, sheet_name: str) -> None:
    """
    初始化时检查组合 int 键（要求位于数据前两列 -> row[0], row[1] 且用 key1:real / key2:real 标记）：
    - 检查 key1/key2 是否为整数、是否在允许范围内
    - 检查组合后的 combined 是否唯一（若重复则抛错并显示真实 Excel 行号，及对应实际 (key1,key2)）
    """
    seen = {}
    for idx, row in enumerate(row_data):
        if len(row) < 2:
            continue
        k1 = row[0].value
        k2 = row[1].value
        excel_row = 7 + idx
        if k1 is None or k2 is None:
            raise RuntimeError(f"行{excel_row} key1/key2 为空")
        try:
            i1 = int(k1)
            i2 = int(k2)
        except Exception:
            raise RuntimeError(f"行{excel_row} key1/key2 不是整数: {k1},{k2}")
        combined = i1 * multiplier + i2
        if combined in seen:
            raise DuplicatePrimaryKeyError(combined, seen[combined], excel_row)
        seen[combined] = excel_row


def check_has_effective_data(row_data: list, field_names: list, data_labels: list) -> bool:
    """
    检查是否至少存在一行包含至少一个非 ignore 且非空的单元格。
    不改变现有生成逻辑，仅用于日志提示。
    """
    if not row_data:
        return False
    for row in row_data:
        for col_index, cell in enumerate(row, start=1):
            if col_index >= len(field_names):
                continue
            if data_labels[col_index] == "ignore":
                continue
            if cell.value not in (None, ""):
                return True
    return False

