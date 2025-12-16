# Author: huhongwei 306463233@qq.com
# MIT License
"""
引用检查模块：处理字段间的引用关系验证。
"""
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..utils.log import log_warn, log_error, log_info
from ..utils.naming_config import (
    JSON_FILE_PATTERN,
    REFERENCE_ALLOW_EMPTY_INT_VALUES,
    REFERENCE_ALLOW_EMPTY_STRING_VALUES,
)
from ..parsing.field_parser import value_type_ok
from ..utils.type_utils import parse_type_annotation


def infer_base_from_value(v: Any) -> Optional[str]:
    """从值推断基础类型"""
    if v is None:
        return None
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    return None


def infer_base_from_set(values: set) -> Optional[str]:
    """从值集合推断基础类型"""
    for x in values:
        t = infer_base_from_value(x)
        if t is not None:
            return t
    return None


def pick_first_nonempty_field(obj: Dict[str, Any]) -> Optional[str]:
    """选择第一条记录中，第一个非空且非容器的字段（包含 id）"""
    for k, v in obj.items():
        if isinstance(v, (list, dict)):
            continue
        if v not in (None, ""):
            return k
    return None


class ReferenceChecker:
    """引用检查器：负责验证工作表之间的引用关系"""
    
    def __init__(self, sheet_name: str, source_file: Optional[str] = None):
        self.sheet_name = sheet_name
        self.source_file = source_file
        self._pending_ref_checks: List[Dict[str, Any]] = []
        self._ref_dict_warned_cols: set[int] = set()
        self._reference_checks_done = False
    
    def add_pending_check(self, check_item: Dict[str, Any]) -> None:
        """添加待检查的引用项"""
        self._pending_ref_checks.append(check_item)
    
    def add_warned_dict_col(self, col_index: int) -> None:
        """记录已警告的字典类型列"""
        self._ref_dict_warned_cols.add(col_index)
    
    def is_dict_col_warned(self, col_index: int) -> bool:
        """检查字典类型列是否已警告"""
        return col_index in self._ref_dict_warned_cols
    
    def clear_pending_checks(self) -> None:
        """清空待检查项（用于多次导出）"""
        self._pending_ref_checks.clear()
        self._reference_checks_done = False
    
    def run_checks(self, search_dirs: List[str], sheet_to_file_map: Optional[Dict[str, str]] = None) -> None:
        """执行引用检查"""
        # 若没有待检查项或已检查过，直接返回，避免重复日志
        if self._reference_checks_done:
            return
        if not self._pending_ref_checks:
            return
        
        cache: Dict[Tuple[str, str], Optional[Tuple[set, Optional[str], str]]] = {}
        # JSON 对象缓存与缺失缓存，避免重复打开文件与重复查找
        json_obj_cache: Dict[str, Any] = {}
        json_missing: set[str] = set()
        # 统一源前缀：优先使用 Excel 文件名
        src = self.source_file
        _src_disp_default = f"[{src}] " if src else f"[{self.sheet_name}] "

        def load_ref_set(sheet: str, field: Optional[str]) -> Optional[Tuple[set, Optional[str], str]]:
            # 当 field 省略时，不使用 (sheet, "__OMIT__") 作为缓存键
            if field is not None:
                key = (sheet, field)
                if key in cache:
                    return cache[key]

            # 若已标记缺失，直接返回
            if sheet in json_missing:
                if field is not None:
                    cache[(sheet, field)] = None
                return None

            # 读取或复用 JSON 对象
            obj = json_obj_cache.get(sheet)
            if obj is None:
                path = None
                for d in filter(None, search_dirs):
                    cand = os.path.join(d, JSON_FILE_PATTERN.format(name=sheet))
                    if os.path.isfile(cand):
                        path = cand
                        break
                if path is None:
                    json_missing.add(sheet)
                    if field is not None:
                        cache[(sheet, field)] = None
                    return None
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        obj = json.load(fp)
                    json_obj_cache[sheet] = obj
                except Exception:
                    json_missing.add(sheet)
                    if field is not None:
                        cache[(sheet, field)] = None
                    return None

            # 确定实际引用列 real_field
            if field is None:
                first_row = next(iter(obj.values()), None)
                if isinstance(first_row, dict):
                    pick = pick_first_nonempty_field(first_row)
                    real_field = pick or "id"
                else:
                    real_field = "id"
            else:
                real_field = field

            # 若该列集合已缓存，直接返回
            key_rf = (sheet, real_field)
            if key_rf in cache:
                if field is not None:
                    cache[(sheet, field)] = cache[key_rf]
                return cache[key_rf]

            # 构建该列的引用集合
            def build_set_for(col: str) -> Tuple[set, Optional[str]]:
                s: set = set()
                for _, row in obj.items():
                    if isinstance(row, dict) and col in row:
                        s.add(row[col])
                return s, infer_base_from_set(s)

            values, base = build_set_for(real_field)
            cache[key_rf] = (values, base, real_field)
            if field is not None:
                cache[(sheet, field)] = cache[key_rf]
            return cache[key_rf]

        any_error = False

        # 小助手：统一构建日志上下文（源/目标/标记）
        def _ctx_parts(ref_sheet: str, ref_real_field: str) -> Tuple[str, str, str]:
            src = self.source_file
            src_disp = f"[{src}] " if src else ""
            target_excel = None
            if sheet_to_file_map and ref_sheet in sheet_to_file_map:
                target_excel = sheet_to_file_map.get(ref_sheet)
            target_disp = f"[{target_excel or f'{ref_sheet}.xlsx'}]"
            marker = f"[{ref_sheet}/{ref_real_field}]"
            return src_disp, target_disp, marker

        for item in self._pending_ref_checks:
            excel_row = item["excel_row"]
            field_name = item["field_name"]
            ref_sheet = item["ref_sheet"]
            ref_field = item["ref_field"]
            kind = item["kind"]
            base = item["base"]
            value = item["value"]

            ref_pack = load_ref_set(ref_sheet, ref_field)
            if ref_pack is None:
                log_warn(f"{_src_disp_default}行{excel_row} 字段 {field_name} 引用 [{ref_sheet}/{ref_field or 'id'}] 未找到目标表 JSON，已跳过检查")
                continue
            ref_values, ref_base, ref_real_field = ref_pack

            def _is_empty_ref(val: Any, base_type: Optional[str]) -> bool:
                if base_type == "int":
                    return isinstance(val, int) and val in REFERENCE_ALLOW_EMPTY_INT_VALUES
                if base_type == "string":
                    return isinstance(val, str) and val in REFERENCE_ALLOW_EMPTY_STRING_VALUES
                return False

            def check_one(v: Any, expected_base: Optional[str]) -> None:
                # 允许空值策略：命中则跳过存在性检查
                if _is_empty_ref(v, expected_base or ref_base):
                    return
                if expected_base and not value_type_ok(expected_base, v):
                    log_error(f"{_src_disp_default}行{excel_row} 字段 {field_name} 类型不匹配，期望 {expected_base}，实际值 {v}")
                    return
                if v not in ref_values:
                    nonlocal any_error
                    any_error = True
                    src_disp, target_disp, marker = _ctx_parts(ref_sheet, ref_real_field)
                    # 格式：[(绿色)源文件] 行X 字段Y 引用值V 不存在于目标文件，但被标记为[Sheet/Field]
                    log_error(f"{src_disp}行{excel_row} 字段{field_name} 引用值{v} 不存在于{target_disp}，但被标记为{marker}")

            # 声明类型与目标列类型不一致也报错（使用与"引用缺失"一致的格式）
            if base and ref_base and base != ref_base:
                any_error = True
                src_disp, target_disp, marker = _ctx_parts(ref_sheet, ref_real_field)
                if kind == "list":
                    log_error(f"{src_disp}行{excel_row} 字段{field_name} 引用类型不匹配 {target_disp}，但被标记为{marker}（目标类型为{ref_base}，本字段声明为 list({base})）")
                else:
                    log_error(f"{src_disp}行{excel_row} 字段{field_name} 引用类型不匹配 {target_disp}，但被标记为{marker}（目标类型为{ref_base}，本字段声明为 {base}）")

            if kind == "scalar":
                check_one(value, base or ref_base)
            elif kind == "list":
                if isinstance(value, list):
                    for ele in value:
                        check_one(ele, base or ref_base)
                else:
                    log_error(f"{_src_disp_default}行{excel_row} 字段 {field_name} 声明为 list({base}) 但实际非列表")

        # 若执行了检查且无任何错误，打印一行成功日志
        if self._pending_ref_checks and not any_error:
            src = self.source_file
            src_disp = f"[{src}] " if src else f"[{self.sheet_name}] "
            log_info(f"{src_disp}没有引用丢失或引用类型不匹配")

        # 标记已完成，避免重复打印
        self._reference_checks_done = True

