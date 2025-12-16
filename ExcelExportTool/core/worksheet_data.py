# Author: huhongwei 306463233@qq.com
# MIT License
"""
工作表数据处理模块：处理单个 Worksheet 的数据导出逻辑。
"""
import json
import os
from typing import Any, Dict, List, Optional, Iterator, Tuple

from ..generation.cs_generation import generate_script_file, generate_enum_file
from ..parsing.excel_processing import read_cell_values, check_repeating_values
from ..parsing.data_processing import convert_to_type
from ..utils.naming_utils import is_valid_csharp_identifier
from ..utils.type_utils import convert_type_to_csharp
from ..utils.log import log_warn, log_info
from ..exceptions import (
    DuplicatePrimaryKeyError,
    CompositeKeyOverflowError,
    InvalidFieldNameError,
    HeaderFormatError,
)
from ..utils.naming_config import (
    JSON_FILE_PATTERN,
    ENUM_KEYS_SUFFIX,
    JSON_SORT_KEYS,
    JSON_ID_FIRST,
    JSON_WARN_TOTAL_BYTES,
    JSON_WARN_RECORD_BYTES,
)
from ..validation.asset_validator import get_asset_validator
from ..utils.user_utils import user_confirm
from ..parsing.field_parser import (
    KEY1_PREFIX_RE,
    KEY2_PREFIX_RE,
    REF_PREFIX_RE,
    ASSET_PREFIX_RE,
    extract_actual_field_name,
    parse_ref_prefix,
    parse_asset_prefix,
    parse_key_prefix,
)
from ..utils.type_utils import parse_type_annotation
from ..validation.worksheet_validator import (
    check_hidden_and_merged,
    check_interface_field_types,
    check_duplicate_enum_keys,
    check_duplicate_composite_keys,
    check_has_effective_data,
    validate_enum_name,
)
from ..validation.reference_checker import ReferenceChecker

# 新增：可选字段统计开关（保持功能不变，默认打印一次汇总；若不需要可改为 False）
_PRINT_FIELD_SUMMARY = True


class WorksheetData:
    """
    处理单个 Worksheet 的数据导出逻辑。
    - 支持三种主键策略：
        1) 字符串枚举主键（need_generate_keys == True）
        2) 单列 int 主键（默认旧行为）
        3) 组合 int 主键（key1:RealName, key2:RealName 出现在 field_names 的前两项）
           组合映射算法： combined = key1 * MULTIPLIER + key2 （无冲突）
    - 当使用前缀配置（key1:xxx / key2:yyy）时，会解析出真实字段名 xxx 和 yyy，
      并在生成的 C# 方法中使用真实字段名作为参数名和注释提示。
    """

    # 组合键参数（默认保证合并结果可装入 int32）
    MAX_KEY2 = 46340         # key2 的上限（exclusive）：0 <= key2 < MAX_KEY2
    MULTIPLIER = MAX_KEY2    # MULTIPLIER = MAX_KEY2

    def __init__(self, worksheet) -> None:
        self.name: str = worksheet.title
        self.worksheet = worksheet
        # 一致性：行长度校验（字段行与类型行长度不一致提前报错）
        # 读取 1..6 行
        self.cell_values: Dict[int, List[Any]] = {
            i: read_cell_values(worksheet, i) for i in range(1, 7)
        }
        self.remarks = self.cell_values[1]
        self.headers = self.cell_values[2]
        self.data_types = self.cell_values[3]
        self.data_labels = self.cell_values[4]
        self.field_names = self.cell_values[5]
        self.default_values = self.cell_values[6]

        # 严格表头检查：确保 1..6 行存在且列数匹配
        for i in range(1, 7):
            row = self.cell_values.get(i)
            if not isinstance(row, list) or len(row) == 0:
                raise HeaderFormatError(self.name, f"表头第{i}行缺失或为空")
        # 字段行长度
        n_fields = len(self.field_names)
        if n_fields == 0:
            raise HeaderFormatError(self.name, "字段行为空或未定义")
        for i in range(1, 7):
            if len(self.cell_values[i]) != n_fields:
                raise HeaderFormatError(self.name, f"第{i}行长度({len(self.cell_values[i])}) 与字段列({n_fields}) 不匹配")

        # 放宽到"告警+自动对齐到字段列数"以兼容历史表头差异
        def _align_list(lst: List[Any], target: int, fill: Any = None, name: str = "") -> List[Any]:
            if len(lst) == target:
                return lst
            if len(lst) < target:
                log_warn(f"{self.name}: {name} 数量({len(lst)}) < 字段列({target})，已以 None 填充")
                return lst + [fill] * (target - len(lst))
            log_warn(f"{self.name}: {name} 数量({len(lst)}) > 字段列({target})，已截断多余列")
            return lst[:target]

        n_fields = len(self.field_names)
        self.remarks = _align_list(self.remarks, n_fields, None, "备注行")
        self.headers = _align_list(self.headers, n_fields, None, "表头行")
        self.data_types = _align_list(self.data_types, n_fields, None, "类型行")
        self.data_labels = _align_list(self.data_labels, n_fields, None, "标签行")
        self.default_values = _align_list(self.default_values, n_fields, None, "默认值行")

        # 检查隐藏行/列与合并单元格：这些可能导致解析与期望不一致
        try:
            check_hidden_and_merged(self.worksheet, self.name)
        except Exception:
            # 检查失败不影响导出流程
            pass

        # 数据行
        self.row_data = list(worksheet.iter_rows(min_row=7, min_col=2))

        # 重复字段检测
        check_repeating_values(self.field_names)

        # 统计(仅用于汇总日志）
        self._field_total = len(self.field_names) - 1 if len(self.field_names) > 0 else 0  # 去掉首列主键列
        self._ignore_count = sum(1 for i in range(len(self.field_names)) if self.data_labels[i] == "ignore")
        self._required_fields = {i for i in range(len(self.field_names)) if self.data_labels[i] == "required"}

        # 检测是否存在有效数据（至少一行中出现非空且未 ignore 的单元格）
        self._has_effective_data = check_has_effective_data(self.row_data, self.field_names, self.data_labels)

        self.need_generate_keys = self._need_generate_keys()
        self.composite_keys = False
        self.composite_key_fields: Dict[str, str] = {}
        self._detect_composite_keys_with_prefixes_in_first_two_columns()
        if self.need_generate_keys:
            check_duplicate_enum_keys(self.row_data, self.name)
        if self.composite_keys:
            check_duplicate_composite_keys(self.row_data, self.MULTIPLIER, self.MAX_KEY2, self.name)
        self.first_int_pk_not_named_id_warned = False

        # 解析字段上的引用前缀 [Sheet/Field]
        self._ref_specs: Dict[int, Tuple[str, Optional[str]]] = {}
        # 解析字段上的资源前缀 [Asset] 或 [Asset:ext]
        self._asset_specs: Dict[int, Optional[str]] = {}
        for i, raw_field_name in enumerate(self.field_names):
            if i == 0:
                continue
            if self.data_labels[i] == "ignore":
                continue
            if not isinstance(raw_field_name, str):
                continue
            # 先解析资源标记 —— 命中后不再作为引用处理，避免混淆
            asset_result = parse_asset_prefix(raw_field_name)
            if asset_result:
                field_name, ext = asset_result
                self._asset_specs[i] = ext
                continue
            # 再解析引用标记
            ref_result = parse_ref_prefix(raw_field_name)
            if ref_result:
                sheet, field = ref_result
                self._ref_specs[i] = (sheet, field)

        # 创建引用检查器
        self._reference_checker = ReferenceChecker(self.name, getattr(self, "source_file", None))

        # 字段命名规范校验（C# 标识符），若不合法则抛错终止导出
        for i in range(len(self.field_names)):
            if i == 0:
                continue
            if self.data_labels[i] == "ignore":
                continue
            raw = self.field_names[i]
            if not isinstance(raw, str):
                continue
            # 取真实字段名（去掉 key1/key2/ref 前缀）
            actual = self._actual_field_name(i)
            if not is_valid_csharp_identifier(actual):
                raise InvalidFieldNameError(actual, i, self.name)

        if not self._has_effective_data:
            log_warn(f"表[{self.name}] 没有有效数据行（将生成空 JSON）。")

        if _PRINT_FIELD_SUMMARY:
            log_info(
                f"[{self.name}] 字段统计: 总列={len(self.field_names)} 可用列(含主键)={len(self.field_names)} "
                f"ignore列={self._ignore_count} required列={len(self._required_fields)}"
            )

        # 新增：自动检测接口字段类型，类型不符时警告并要求用户确认
        props = self._get_properties_dict()
        check_interface_field_types(self.name, props)

    def _need_generate_keys(self) -> bool:
        """判断是否需要为数据行生成自增 key（原逻辑）"""
        property_types = self._get_properties_dict()
        return next(iter(property_types.values()), None) == "string"

    def _get_properties_dict(self) -> Dict[str, str]:
        """
        字段名 -> C# 类型
        注意：字段名可能包含前缀 'key1:' / 'key2:'，这里会返回真实字段名（去掉前缀）
        保持原来 i>0 的约定。
        """
        result = {}
        for i in self._iter_effective_field_indices():
            actual_name = self._actual_field_name(i)
            result[actual_name] = convert_type_to_csharp(self.data_types[i])
        return result

    def _get_property_remarks(self) -> Dict[str, str]:
        """字段名 -> 注释（表头: 备注），字段名使用真实名字（去掉 key1:/key2: 前缀）"""
        result = {}
        for i in self._iter_effective_field_indices():
            actual_name = self._actual_field_name(i)
            result[actual_name] = (
                f"{self.headers[i]}: {self.remarks[i]}" if self.remarks[i] else self.headers[i]
            )
        return result

    def _iter_effective_field_indices(self) -> Iterator[int]:
        """生成导出所需的有效列索引（排除 ignore 且不含首列主键）。"""
        for i in range(len(self.field_names)):
            if self.data_labels[i] != "ignore" and i > 0:
                yield i

    def _actual_field_name(self, field_index: int) -> str:
        """
        返回 field_names[field_index] 对应的"真实字段名"：
        - 如果字段是 'key1:xxx' 或 'key2:yyy' 格式，返回 xxx / yyy（不包含前缀）
        - 否则返回原始 field_names[field_index]
        注意：field_index 对应你原来使用的索引（从 0 开始），generate_json 使用 enumerate(row, start=1) 时要匹配该索引。
        """
        raw = self.field_names[field_index]
        return extract_actual_field_name(raw)

    def _detect_composite_keys_with_prefixes_in_first_two_columns(self) -> None:
        """
        强制检查：
          - field_names[1] 以 key1:RealName 格式出现（不区分大小写）
          - field_names[2] 以 key2:RealName 格式出现（不区分大小写）
          - data_types[1] 与 data_types[2] 都包含 "int"
        并在 self.composite_key_fields 中保存真实字段名：
          self.composite_key_fields = {"key1": "id", "key2": "group"}
        """
        try:
            if len(self.field_names) <= 2:
                self.composite_keys = False
                return

            f1 = self.field_names[1]
            f2 = self.field_names[2]
            if not (isinstance(f1, str) and isinstance(f2, str)):
                self.composite_keys = False
                return

            key1_result = parse_key_prefix(f1)
            key2_result = parse_key_prefix(f2)
            
            if not (key1_result and key2_result and key1_result[0] == "key1" and key2_result[0] == "key2"):
                self.composite_keys = False
                return

            dt1 = self.data_types[1] if len(self.data_types) > 1 else None
            dt2 = self.data_types[2] if len(self.data_types) > 2 else None
            if not (isinstance(dt1, str) and isinstance(dt2, str) and "int" in dt1.strip().lower() and "int" in dt2.strip().lower()):
                self.composite_keys = False
                return

            # 解析真实字段名并启用 composite_keys
            real1 = key1_result[1]
            real2 = key2_result[1]
            if not real1 or not real2:
                self.composite_keys = False
                return

            self.composite_keys = True
            self.composite_key_fields = {"key1": real1, "key2": real2}
        except Exception:
            self.composite_keys = False
            self.composite_key_fields = {}

    def _generate_enum_keys_csfile(self, output_folder: str) -> None:
        """当需要 string 枚举键时才调用（保留原有实现）"""
        enum_type_name = f"{self.name}{ENUM_KEYS_SUFFIX}"
        enum_names = []
        enum_values = []
        idx_val = 0
        for idx, row in enumerate(self.row_data):
            if not row:
                continue
            val = row[0].value
            validate_enum_name(val, 7 + idx)
            enum_names.append(val)
            enum_values.append(idx_val)
            idx_val += 1
        generate_enum_file(enum_type_name, enum_names, enum_values, None, "Data.TableScript", output_folder)

    def generate_json(self, output_folder: str) -> None:
        """将表格数据导出为 JSON 文件（支持单列 int 主键 / 自动生成键 / 以及组合键）。
        这里同时确保给每条记录填充 info.id：
            - 字符串主键（枚举）：id = 序号（枚举 int 值）
            - 组合键：id = key1*MULTIPLIER + key2
            - 单列 int 主键：id = 第一列的 int 值；若第一列字段名不是 'id' 则打印一次警告
        """
        # 避免重复收集：若同一张表导出到多个目录，这里清空后重新收集一次
        self._reference_checker.clear_pending_checks()

        data: Dict[Any, Dict[str, Any]] = {}
        serial_key = 0
        first_real = self._actual_field_name(1) if len(self.field_names) > 1 else None
        used_keys = {}

        # 新增：统计 required 缺失次数（虽然缺失会抛错，此计数主要用于未来扩展；保持现功能）
        required_missing_count = 0

        # To avoid memory explosion, monitor serialized sizes.
        # We check per-record serialized size opportunistically and full-JSON size after serialization.
        record_check_interval = 50  # 每多少条记录进行一次轻量检查（默认每50条）
        oversized_record_warned = False

        for row_idx, row in enumerate(self.row_data):
            if not row:
                continue
            excel_row = 7 + row_idx
            # 处理主键
            if self.need_generate_keys:
                row_key = serial_key
                serial_key += 1
            elif self.composite_keys:
                try:
                    k1 = int(row[0].value)
                    k2 = int(row[1].value)
                except Exception:
                    raise RuntimeError(f"行{excel_row} 无法解析组合键 int")
                if not (0 <= k1 < self.MAX_KEY2 and 0 <= k2 < self.MAX_KEY2):
                    raise RuntimeError(f"行{excel_row} 组合键超范围 0~{self.MAX_KEY2-1}")
                row_key = k1 * self.MULTIPLIER + k2
                if row_key >= 2**31:
                    raise CompositeKeyOverflowError(row_key)
            else:
                try:
                    row_key = int(row[0].value)
                except Exception:
                    raise RuntimeError(f"行{excel_row} 主键非 int: {row[0].value}")
                if (isinstance(first_real, str)
                        and first_real.lower() != "id"
                        and not self.first_int_pk_not_named_id_warned):
                    log_warn(f"表[{self.name}] 第一列视为主键但字段名不是 id，已写入 id 属性。建议修改表头。")
                    self.first_int_pk_not_named_id_warned = True

            if row_key in used_keys:
                raise DuplicatePrimaryKeyError(row_key, used_keys[row_key], excel_row)
            used_keys[row_key] = excel_row

            # 保持列顺序：按 Excel 顺序构建
            if JSON_ID_FIRST:
                row_obj = {"id": int(row_key)}
            else:
                row_obj = {}

            for col_index, cell in enumerate(row, start=1):
                if col_index >= len(self.field_names):
                    continue
                if self.data_labels[col_index] == "ignore":
                    continue
                data_name = self._actual_field_name(col_index)
                type_str = self.data_types[col_index]
                default_value = self.default_values[col_index]
                cell_value = cell.value

                if cell_value is None:
                    if default_value is None and self.data_labels[col_index] == "required":
                        required_missing_count += 1
                        raise RuntimeError(f"{data_name} required 但值为空且无默认值 (行{excel_row})")
                    value = convert_to_type(type_str, default_value, data_name, self.name)
                else:
                    value = convert_to_type(type_str, cell_value, data_name, self.name)
                row_obj[data_name] = value

                # 资源字段校验：[Asset] 或 [Asset:ext]，值为无扩展名文件名；严格大小写匹配文件名，扩展名忽略大小写
                if col_index in getattr(self, "_asset_specs", {}):
                    # 仅对 string 或 list(string) 做校验；其他类型跳过
                    try:
                        _kind, _base = parse_type_annotation(type_str)
                    except Exception:
                        _kind, _base = ("scalar", None)
                    required_ext = self._asset_specs.get(col_index)
                    validator = get_asset_validator()
                    if validator is None:
                        # 未配置或解析失败：提示一次全局警告后跳过（每字段每行不重复提示）
                        if not hasattr(self, "_asset_validator_missing_warned"):
                            log_warn(f"[{self.name}] 未配置 YooAsset 收集设置或解析失败，已跳过 [Asset] 字段校验。请在 sheet_config.json 配置 yooasset.collector_setting")
                            setattr(self, "_asset_validator_missing_warned", True)
                    else:
                        def _check_one_filename(fname: Any):
                            if not isinstance(fname, str) or not fname.strip():
                                return
                            if validator is None:
                                return
                            ok = validator.exists_base_name(fname.strip(), required_ext)
                            if not ok:
                                msg = f"[{self.name}] 行{excel_row} 字段 {data_name} 标记为[Asset{(':'+required_ext) if required_ext else ''}]，在任一收集路径下未找到文件名为 '{fname}' 的资源"
                                if validator.strict:
                                    # 严格模式：直接报错中断
                                    raise RuntimeError(msg)
                                else:
                                    log_warn(msg)

                        if _kind == "list" and isinstance(value, list):
                            for ele in value:
                                _check_one_filename(ele)
                        else:
                            _check_one_filename(value)

                # 收集引用检查
                if col_index in self._ref_specs:
                    ref_sheet, ref_field = self._ref_specs[col_index]
                    kind, base = parse_type_annotation(type_str)
                    if kind == "dict":
                        if not self._reference_checker.is_dict_col_warned(col_index):
                            log_warn(f"[{self.name}] 字段 {data_name} 标注了引用 [{ref_sheet}/{ref_field or 'id'}] 但类型为字典，跳过检查")
                            self._reference_checker.add_warned_dict_col(col_index)
                    else:
                        # 记录此行的待检查项
                        self._reference_checker.add_pending_check({
                            "excel_row": excel_row,
                            "field_name": data_name,
                            "ref_sheet": ref_sheet,
                            "ref_field": ref_field,  # None -> id
                            "kind": kind,
                            "base": base,
                            "value": value,
                        })

            if not JSON_ID_FIRST:
                row_obj["id"] = int(row_key)
            data[row_key] = row_obj

            # Opportunistic per-record size check (only until we warn once to save time)
            if (not oversized_record_warned) and (row_idx % record_check_interval == 0):
                try:
                    # 快速测量单条记录序列化尺寸
                    rec_bytes = json.dumps(row_obj, ensure_ascii=False).encode('utf-8')
                    if len(rec_bytes) > JSON_WARN_RECORD_BYTES:
                        log_warn(f"[{self.name}] 行{excel_row} 序列化单条记录大小过大: {len(rec_bytes)} bytes (> {JSON_WARN_RECORD_BYTES}). 此表可能会导致内存或磁盘问题。")
                        oversized_record_warned = True
                except Exception:
                    # 不应阻塞主流程，忽略序列化异常的大小检查
                    pass

        file_content = json.dumps(
            data,
            ensure_ascii=False,
            indent=4,
            sort_keys=JSON_SORT_KEYS
        )

        # 全量 JSON 大小检查
        try:
            total_bytes = file_content.encode('utf-8')
            total_len = len(total_bytes)
            if total_len > JSON_WARN_TOTAL_BYTES:
                log_warn(f"[{self.name}] 序列化后的 JSON 总大小为 {total_len} bytes (> {JSON_WARN_TOTAL_BYTES}). 请检查表格是否过大或包含不应导出的数据。")
        except Exception:
            # 不要阻塞写入：继续写文件并记录日志
            log_warn(f"[{self.name}] 无法计算序列化后的 JSON 大小")
        from ..generation.cs_generation import write_to_file
        file_path = os.path.join(output_folder, JSON_FILE_PATTERN.format(name=self.name))
        write_to_file(file_content, file_path)

        if _PRINT_FIELD_SUMMARY:
            log_info(f"[{self.name}] 导出完成: 行数={len(data)} required缺失={required_missing_count}")

    def run_reference_checks(self, search_dirs: List[str], sheet_to_file_map: Optional[Dict[str, str]] = None) -> None:
        """执行引用检查"""
        self._reference_checker.run_checks(search_dirs, sheet_to_file_map)

    def generate_script(self, output_folder: str) -> None:
        """
        生成 C# 脚本（必要时生成枚举 Key 文件）。
        会把 composite_keys 与 MULTIPLIER 及 composite_key_fields 传给 cs 生成器，
        以便生成的 C# 方法使用真实字段名作为参数名。
        """
        props = self._get_properties_dict()
        remarks = self._get_property_remarks()
        generate_script_file(
            self.name,
            props,
            remarks,
            output_folder,
            self.need_generate_keys,
            composite_keys=self.composite_keys,
            composite_multiplier=self.MULTIPLIER,
            composite_key_fields=self.composite_key_fields if self.composite_keys else None
        )
        if self.need_generate_keys:
            self._generate_enum_keys_csfile(output_folder)
