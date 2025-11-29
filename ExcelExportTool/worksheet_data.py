# Author: huhongwei 306463233@qq.com
# MIT License
import json
import re
import os
from typing import Any, Dict, List, Optional, Tuple, Iterator
from collections import defaultdict

from .cs_generation import generate_script_file, generate_enum_file
from .excel_processing import read_cell_values, check_repeating_values
from .data_processing import convert_to_type, available_csharp_enum_name
from .naming_utils import is_valid_csharp_identifier
from .type_utils import parse_type_annotation, convert_type_to_csharp
from .log import log_warn, log_error, log_info
from .exceptions import (
    InvalidEnumNameError,
    DuplicatePrimaryKeyError,
    CompositeKeyOverflowError,
    InvalidFieldNameError,
    HeaderFormatError,
)
from .naming_config import (
    JSON_FILE_PATTERN,
    ENUM_KEYS_SUFFIX,
    JSON_SORT_KEYS,
    JSON_ID_FIRST,
    REFERENCE_ALLOW_EMPTY_INT_VALUES,
    REFERENCE_ALLOW_EMPTY_STRING_VALUES,
    JSON_WARN_TOTAL_BYTES,
    JSON_WARN_RECORD_BYTES,
)

# 新增：可选字段统计开关（保持功能不变，默认打印一次汇总；若不需要可改为 False）
_PRINT_FIELD_SUMMARY = True

# 资产校验：全局缓存（同一次导表仅解析与索引一次）
_ASSET_VALIDATOR = None  # type: ignore
_ASSET_VALIDATOR_KEY: Optional[Tuple[str, bool]] = None  # (collector_setting_path, strict)

class _AssetEntry:
    __slots__ = ("base", "ext", "path", "root")
    def __init__(self, base: str, ext: str, path: str, root: str) -> None:
        # base：不含扩展名，保留实际大小写
        # ext：不带点的小写（如 'png','prefab'）
        self.base = base
        self.ext = ext
        self.path = path
        self.root = root

class AssetValidator:
    def __init__(self, collector_setting: str, strict: bool = False) -> None:
        self.collector_setting = collector_setting
        self.strict = bool(strict)
        self.project_root = self._infer_project_root(collector_setting)
        self.roots = self._parse_collect_paths(collector_setting)
        self._index: Dict[str, List[_AssetEntry]] = {}
        if self.project_root and self.roots:
            self._build_index()

    def _infer_project_root(self, collector_setting: str) -> str:
        try:
            p = os.path.abspath(collector_setting).replace("\\", "/")
            parts = p.split("/")
            if "Assets" in parts:
                idx = parts.index("Assets")
                root = "/".join(parts[:idx])
                return root if root else "/"
        except Exception:
            pass
        return ""

    def _parse_collect_paths(self, collector_setting: str) -> List[str]:
        paths: List[str] = []
        try:
            with open(collector_setting, "r", encoding="utf-8") as f:
                for line in f:
                    # 匹配形如：  - CollectPath: Assets/...
                    m = re.search(r"CollectPath:\s*(Assets/[^\r\n]+)", line)
                    if m:
                        path = m.group(1).strip()
                        # 统一去除尾部斜杠
                        if path.endswith("/"):
                            path = path[:-1]
                        if path not in paths:
                            paths.append(path)
        except Exception:
            return []
        return paths

    def _build_index(self) -> None:
        proj = self.project_root
        idx: Dict[str, List[_AssetEntry]] = {}
        for root in self.roots:
            abs_root = os.path.join(proj, root.replace("/", os.sep))
            if not os.path.isdir(abs_root):
                continue
            for dirpath, _dirnames, filenames in os.walk(abs_root):
                for fn in filenames:
                    if fn.endswith(".meta"):
                        continue
                    base, ext = os.path.splitext(fn)
                    ext = (ext[1:].lower() if ext else "")  # 去掉点
                    entry = _AssetEntry(base=base, ext=ext, path=os.path.join(dirpath, fn), root=root)
                    key = base.lower()
                    idx.setdefault(key, []).append(entry)
        self._index = idx

    def exists_base_name(self, base_name: str, required_ext: Optional[str]) -> bool:
        if not self._index:
            return False
        key = base_name.lower().strip()
        cand = self._index.get(key, [])
        if not cand:
            return False
        # 文件名严格大小写匹配；扩展名忽略大小写
        if required_ext:
            req = required_ext.strip().lstrip(".").lower()
            return any(e.base == base_name and e.ext == req for e in cand)
        else:
            return any(e.base == base_name for e in cand)


def _load_sheet_config_for_assets() -> Optional[Dict[str, Any]]:
    """按优先级加载配置：
    1) 环境变量 SHEETEASE_CONFIG_JSON（直接提供JSON字符串）
    2) 环境变量 SHEETEASE_CONFIG_PATH（指定配置文件路径）
    3) 候选路径：CWD/sheet_config.json 与 仓库根/sheet_config.json
    """
    # 1) 直接从环境变量读取 JSON 字符串
    try:
        env_json = os.environ.get('SHEETEASE_CONFIG_JSON')
        if env_json:
            return json.loads(env_json)
    except Exception:
        pass
    # 2) 指定路径
    try:
        env_path = os.environ.get('SHEETEASE_CONFIG_PATH')
        if env_path and os.path.isfile(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    # 3) 常规候选
    candidates = []
    try:
        candidates.append(os.path.join(os.getcwd(), "sheet_config.json"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sheet_config.json"))
    except Exception:
        pass
    for p in candidates:
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return None


def _get_asset_validator() -> Optional[AssetValidator]:
    """按当前配置返回（并必要时重建）资产校验器。
    若切换了 collector 路径或 strict 选项，会自动丢弃旧缓存并重建，避免 GUI 多次运行时使用旧配置。
    """
    global _ASSET_VALIDATOR, _ASSET_VALIDATOR_KEY
    cfg = _load_sheet_config_for_assets()
    if not cfg:
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None
    yoo = cfg.get("yooasset") or {}
    collector = yoo.get("collector_setting")
    strict = bool(yoo.get("strict", False))
    # 当 collector 不存在时直接返回 None（并清空缓存）
    if not collector or not os.path.isfile(collector):
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None
    key = (os.path.abspath(collector), strict)
    if _ASSET_VALIDATOR is not None and _ASSET_VALIDATOR_KEY == key:
        return _ASSET_VALIDATOR
    # 重建
    try:
        validator = AssetValidator(collector, strict=strict)
        if not validator.roots:
            _ASSET_VALIDATOR = None
            _ASSET_VALIDATOR_KEY = None
            return None
        _ASSET_VALIDATOR = validator
        _ASSET_VALIDATOR_KEY = key
        return _ASSET_VALIDATOR
    except Exception:
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None


def user_confirm(msg: str, title: str = "用户确认") -> bool:
    """
    统一的用户确认函数：命令行用input，GUI用弹窗。
    返回True表示继续，False表示取消。
    """
    import os
    if os.environ.get('SHEETEASE_GUI', '') == '1':
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk._default_root or tk.Tk()
            root.withdraw()
            res = messagebox.askyesno(title, msg)
            return bool(res)
        except Exception:
            print(msg)
            ans = input().strip().lower()
            return ans in ("y", "yes")
    else:
        print(msg)
        ans = input().strip().lower()
        return ans in ("y", "yes")


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

    KEY1_PREFIX_RE = re.compile(r"^\s*key1\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
    KEY2_PREFIX_RE = re.compile(r"^\s*key2\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
    # [Sheet/Field]FieldName 或 [Sheet]FieldName（省略 Field -> 默认 id）
    # 引用标记：[Sheet/Field]FieldName（Sheet 名不允许包含 ':'，避免与 [Asset:ext] 混淆）
    REF_PREFIX_RE = re.compile(r"^\s*\[(?P<sheet>[^:/\]]+)(?:/(?P<field>[^\]]+))?\]\s*(?P<name>.+)$")
    # [Asset]FieldName 或 [Asset:png]FieldName —— 资源文件校验标记（文件名不含扩展名，严格大小写匹配文件名，扩展名忽略大小写）
    ASSET_PREFIX_RE = re.compile(r"^\s*\[(?:asset)(?::(?P<ext>[A-Za-z0-9_]+))?\]\s*(?P<name>.+)$", re.IGNORECASE)

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

        # 放宽到“告警+自动对齐到字段列数”以兼容历史表头差异
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
            self._check_hidden_and_merged()
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
        self._has_effective_data = self._check_has_effective_data()

        self.need_generate_keys = self._need_generate_keys()
        self.composite_keys = False
        self.composite_key_fields: Dict[str, str] = {}
        self._detect_composite_keys_with_prefixes_in_first_two_columns()
        if self.need_generate_keys:
            self._check_duplicate_enum_keys()
        if self.composite_keys:
            self._check_duplicate_composite_keys()
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
            am = self.ASSET_PREFIX_RE.match(raw_field_name)
            if am:
                ext = am.group("ext")
                self._asset_specs[i] = (ext.strip().lower() if isinstance(ext, str) and ext.strip() else None)
                continue
            # 再解析引用标记
            m = self.REF_PREFIX_RE.match(raw_field_name)
            if m:
                sheet = m.group("sheet").strip()
                field = m.group("field")
                field = field.strip() if field else None
                self._ref_specs[i] = (sheet, field)

        # 供 generate_json 收集待检查项
        self._pending_ref_checks: List[Dict[str, Any]] = []
        self._ref_dict_warned_cols: set[int] = set()

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
        self._check_interface_field_types()

    def _check_hidden_and_merged(self) -> None:
        """检测隐藏行/列与合并单元格，给出可能导致解析异常的提示。"""
        ws = self.worksheet
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
            _msg = f"[{self.name}] 检测到隐藏行: {sample}{more}。隐藏行可能导致导出结果与期望不一致"
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
            _msg = f"[{self.name}] 检测到隐藏列: {sample}{more}。隐藏列可能导致导出结果与期望不一致"
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
            _msg = f"[{self.name}] 检测到合并单元格: {sample}{more}。合并区域可能导致读取表头或数据对齐异常，建议取消合并"
            log_warn(_msg, immediate=True)
            log_warn(_msg, immediate=False)

    def _check_interface_field_types(self):
        """
        自动解析 IConfigRawInfo.cs，获取接口字段及类型，对所有同名字段类型不符的都进行检查和提示。
        """
        import re
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
        props = self._get_properties_dict()
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
            raise RuntimeError(f"表[{self.name}] 字段类型错误：\n{detail}")

        # 2) 其他接口字段保持原有“提示并确认”的流程
        wrongs = []
        for fname, ftype in interface_fields.items():
            if fname in ('id', 'name'):
                continue  # 已做强制检查
            actual_type = props.get(fname)
            if actual_type is not None and actual_type.lower() != ftype:
                wrongs.append((fname, actual_type, ftype))
        if wrongs:
            msg = f"表[{self.name}] 字段类型警告：\n"
            for fname, actual, expect in wrongs:
                msg += f"  - {fname} 字段类型为 {actual}，应为 {expect}\n"
            msg += "这可能导致生成的 C# 脚本无法通过编译。\n是否继续导出？(y/n)"
            if user_confirm(msg):
                log_warn("用户选择继续导出")
            else:
                raise RuntimeError("用户取消导出：接口字段类型不符")

    def _check_id_name_field_types(self):
        """
        检查 id 字段类型是否为 int，name 字段类型是否为 string。
        类型不符时警告，并要求用户确认，用户拒绝则抛异常终止导出。
        """
        props = self._get_properties_dict()
        id_type = props.get('id')
        name_type = props.get('name')
        id_wrong = id_type is not None and id_type.lower() != 'int'
        name_wrong = name_type is not None and name_type.lower() != 'string'
        if id_wrong or name_wrong:
            msg = f"表[{self.name}] 字段类型警告：\n"
            if id_wrong:
                msg += f"  - id 字段类型为 {id_type}，应为 int\n"
            if name_wrong:
                msg += f"  - name 字段类型为 {name_type}，应为 string\n"
            msg += "这将导致生成的 C# 脚本无法通过编译。\n是否继续导出？(y/n)"
            if user_confirm(msg):
                log_warn("用户选择继续导出")
            else:
                raise RuntimeError("用户取消导出：id/name 字段类型不符")

    def _need_generate_keys(self) -> bool:
        """判断是否需要为数据行生成自增 key（原逻辑）"""
        property_types = self._get_properties_dict()
        return next(iter(property_types.values()), None) == "string"

    @staticmethod
    def _convert_to_csharp_type(type_str: str) -> str:
        """Excel 类型 -> C# 类型"""
        type_mappings = {"list": "List", "dict": "Dictionary"}
        for key, value in type_mappings.items():
            type_str = type_str.replace(key, value)
        return type_str.replace("(", "<").replace(")", ">")

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
        返回 field_names[field_index] 对应的“真实字段名”：
        - 如果字段是 'key1:xxx' 或 'key2:yyy' 格式，返回 xxx / yyy（不包含前缀）
        - 否则返回原始 field_names[field_index]
        注意：field_index 对应你原来使用的索引（从 0 开始），generate_json 使用 enumerate(row, start=1) 时要匹配该索引。
        """
        raw = self.field_names[field_index]
        if not isinstance(raw, str):
            return str(raw)
        m1 = self.KEY1_PREFIX_RE.match(raw)
        if m1:
            return m1.group("name").strip()
        m2 = self.KEY2_PREFIX_RE.match(raw)
        if m2:
            return m2.group("name").strip()
        # 去掉资源前缀 [Asset] / [Asset:ext]
        m_asset = self.ASSET_PREFIX_RE.match(raw)
        if m_asset:
            return m_asset.group("name").strip()
        # 去掉引用前缀 [Sheet/Field]
        m3 = self.REF_PREFIX_RE.match(raw)
        if m3:
            return m3.group("name").strip()
        return raw

    @staticmethod
    def _parse_type_annotation(type_str: str) -> Tuple[str, Optional[str]]:
        t = (type_str or "").strip().lower()
        def base_norm(s: str) -> str:
            s = s.strip().lower()
            if s in ("int", "int32", "integer"): return "int"
            if s in ("float", "double"): return "float"
            if s in ("str", "string"): return "string"
            if s in ("bool", "boolean"): return "bool"
            return s
        if t.startswith("list(") and t.endswith(")"):
            return "list", base_norm(t[5:-1])
        if t.startswith("dict(") and t.endswith(")"):
            return "dict", None
        return "scalar", base_norm(t)

    @staticmethod
    def _value_type_ok(base: str, v: Any) -> bool:
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

            m1 = self.KEY1_PREFIX_RE.match(f1)
            m2 = self.KEY2_PREFIX_RE.match(f2)
            if not (m1 and m2):
                self.composite_keys = False
                return

            dt1 = self.data_types[1] if len(self.data_types) > 1 else None
            dt2 = self.data_types[2] if len(self.data_types) > 2 else None
            if not (isinstance(dt1, str) and isinstance(dt2, str) and "int" in dt1.strip().lower() and "int" in dt2.strip().lower()):
                self.composite_keys = False
                return

            # 解析真实字段名并启用 composite_keys
            real1 = m1.group("name").strip()
            real2 = m2.group("name").strip()
            if not real1 or not real2:
                self.composite_keys = False
                return

            self.composite_keys = True
            self.composite_key_fields = {"key1": real1, "key2": real2}
        except Exception:
            self.composite_keys = False
            self.composite_key_fields = {}

    def _validate_enum_name(self, name: str, excel_row: int) -> None:
        """检查枚举名是否合法（excel_row 为真实 Excel 行号，用于错误提示）"""
        if not available_csharp_enum_name(name):
            raise InvalidEnumNameError(name, excel_row)

    def _check_duplicate_enum_keys(self) -> None:
        """
        初始化时检查用于生成枚举的首列（字符串主键）：
        - 验证每个名字是否合法
        - 收集出现的 Excel 行号，若重复则抛错（显示真实 Excel 行号）
        """
        name_rows = defaultdict(list)
        for idx, row in enumerate(self.row_data):
            if not row:
                continue
            val = row[0].value
            excel_row = 7 + idx
            self._validate_enum_name(val, excel_row)
            name_rows[val].append(excel_row)
        dup = {k: v for k, v in name_rows.items() if len(v) > 1}
        if dup:
            lines = "; ".join(f"{k} -> 行{v}" for k, v in dup.items())
            raise InvalidEnumNameError(f"重复的字符串主键: {lines}", -1)

    def _check_duplicate_composite_keys(self) -> None:
        """
        初始化时检查组合 int 键（要求位于数据前两列 -> row[0], row[1] 且用 key1:real / key2:real 标记）：
        - 检查 key1/key2 是否为整数、是否在允许范围内
        - 检查组合后的 combined 是否唯一（若重复则抛错并显示真实 Excel 行号，及对应实际 (key1,key2)）
        """
        seen = {}
        for idx, row in enumerate(self.row_data):
            if len(row) < 2:
                continue
            k1 = row[0].value
            k2 = row[1].value
            excel_row = 7 + idx
            if k1 is None or k2 is None:
                raise RuntimeError(f"行{excel_row} key1/key2 为空")
            try:
                i1 = int(k1); i2 = int(k2)
            except Exception:
                raise RuntimeError(f"行{excel_row} key1/key2 不是整数: {k1},{k2}")
            combined = i1 * self.MULTIPLIER + i2
            if combined in seen:
                raise DuplicatePrimaryKeyError(combined, seen[combined], excel_row)
            seen[combined] = excel_row

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
            self._validate_enum_name(val, 7 + idx)
            enum_names.append(val)
            enum_values.append(idx_val)
            idx_val += 1
        generate_enum_file(enum_type_name, enum_names, enum_values, None, "Data.TableScript", output_folder)

    def _check_has_effective_data(self) -> bool:
        """
        检查是否至少存在一行包含至少一个非 ignore 且非空的单元格。
        不改变现有生成逻辑，仅用于日志提示。
        """
        if not self.row_data:
            return False
        for row in self.row_data:
            for col_index, cell in enumerate(row, start=1):
                if col_index >= len(self.field_names):
                    continue
                if self.data_labels[col_index] == "ignore":
                    continue
                if cell.value not in (None, ""):
                    return True
        return False

    def generate_json(self, output_folder: str) -> None:
        """将表格数据导出为 JSON 文件（支持单列 int 主键 / 自动生成键 / 以及组合键）。
        这里同时确保给每条记录填充 info.id：
            - 字符串主键（枚举）：id = 序号（枚举 int 值）
            - 组合键：id = key1*MULTIPLIER + key2
            - 单列 int 主键：id = 第一列的 int 值；若第一列字段名不是 'id' 则打印一次警告
        """
        # 避免重复收集：若同一张表导出到多个目录，这里清空后重新收集一次
        if hasattr(self, "_pending_ref_checks"):
            self._pending_ref_checks.clear()
        # 允许同一实例多次导出后再次执行引用检查
        self._reference_checks_done = False

        data: Dict[Any, Dict[str, Any]] = {}
        serial_key = 0
        first_real = self._actual_field_name(1) if len(self.field_names) > 1 else None
        used_keys = {}

        # 新增：统计 required 缺失次数（虽然缺失会抛错，此计数主要用于未来扩展；保持现功能）
        required_missing_count = 0

        # 截断日志辅助函数，避免在循环内重复定义
        def _short(v, limit=60):
            s = str(v)
            return s if len(s) <= limit else s[:limit] + "..."

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
                        _kind, _base = self._parse_type_annotation(type_str)
                    except Exception:
                        _kind, _base = ("scalar", None)
                    required_ext = self._asset_specs.get(col_index)
                    validator = _get_asset_validator()
                    if validator is None:
                        # 未配置或解析失败：提示一次全局警告后跳过（每字段每行不重复提示）
                        if not hasattr(self, "_asset_validator_missing_warned"):
                            log_warn(f"[{self.name}] 未配置 YooAsset 收集设置或解析失败，已跳过 [Asset] 字段校验。请在 sheet_config.json 配置 yooasset.collector_setting")
                            setattr(self, "_asset_validator_missing_warned", True)
                    else:
                        def _check_one_filename(fname: Any):
                            if not isinstance(fname, str) or not fname.strip():
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
                    kind, base = self._parse_type_annotation(type_str)
                    if kind == "dict":
                        if col_index not in self._ref_dict_warned_cols:
                            log_warn(f"[{self.name}] 字段 {data_name} 标注了引用 [{ref_sheet}/{ref_field or 'id'}] 但类型为字典，跳过检查")
                            self._ref_dict_warned_cols.add(col_index)
                    else:
                        # 记录此行的待检查项
                        self._pending_ref_checks.append({
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
        from .cs_generation import write_to_file
        file_path = os.path.join(output_folder, JSON_FILE_PATTERN.format(name=self.name))
        write_to_file(file_content, file_path)

        if _PRINT_FIELD_SUMMARY:
            log_info(f"[{self.name}] 导出完成: 行数={len(data)} required缺失={required_missing_count}")

    def run_reference_checks(self, search_dirs: List[str], sheet_to_file_map: Optional[Dict[str, str]] = None) -> None:
        # 若没有待检查项或已检查过，直接返回，避免重复日志
        if getattr(self, "_reference_checks_done", False):
            return
        if not self._pending_ref_checks:
            return
        cache: Dict[Tuple[str, str], Optional[Tuple[set, Optional[str], str]]] = {}
        # JSON 对象缓存与缺失缓存，避免重复打开文件与重复查找
        json_obj_cache: Dict[str, Any] = {}
        json_missing: set[str] = set()
        # 统一源前缀：优先使用 Excel 文件名
        src = getattr(self, "source_file", None)
        _src_disp_default = f"[{src}] " if src else f"[{self.name}] "

        def _infer_base_from_value(v: Any) -> Optional[str]:
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

        def _infer_base_from_set(values: set) -> Optional[str]:
            for x in values:
                t = _infer_base_from_value(x)
                if t is not None:
                    return t
            return None

        def _pick_first_nonempty_field(obj: Dict[str, Any]) -> Optional[str]:
            # 选择第一条记录中，第一个非空且非容器的字段（包含 id）
            for k, v in obj.items():
                if isinstance(v, (list, dict)):
                    continue
                if v not in (None, ""):
                    return k
            return None

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
                    pick = _pick_first_nonempty_field(first_row)
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
                return s, _infer_base_from_set(s)

            values, base = build_set_for(real_field)
            cache[key_rf] = (values, base, real_field)
            if field is not None:
                cache[(sheet, field)] = cache[key_rf]
            return cache[key_rf]

        any_error = False

        # 小助手：统一构建日志上下文（源/目标/标记）
        def _ctx_parts(ref_sheet: str, ref_real_field: str) -> Tuple[str, str, str]:
            src = getattr(self, "source_file", None)
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
                if expected_base and not self._value_type_ok(expected_base, v):
                    log_error(f"{_src_disp_default}行{excel_row} 字段 {field_name} 类型不匹配，期望 {expected_base}，实际值 {v}")
                    return
                if v not in ref_values:
                    nonlocal any_error
                    any_error = True
                    src_disp, target_disp, marker = _ctx_parts(ref_sheet, ref_real_field)
                    # 格式：[(绿色)源文件] 行X 字段Y 引用值V 不存在于目标文件，但被标记为[Sheet/Field]
                    log_error(f"{src_disp}行{excel_row} 字段{field_name} 引用值{v} 不存在于{target_disp}，但被标记为{marker}")

            # 声明类型与目标列类型不一致也报错（使用与“引用缺失”一致的格式）
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
            src = getattr(self, "source_file", None)
            src_disp = f"[{src}] " if src else f"[{self.name}] "
            log_info(f"{src_disp}没有引用丢失或引用类型不匹配")

        # 标记已完成，避免重复打印
        self._reference_checks_done = True

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
