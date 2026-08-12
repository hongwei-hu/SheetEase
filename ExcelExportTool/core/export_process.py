# Author: huhongwei 306463233@qq.com
# MIT License
import hashlib
import json
import time
import openpyxl
from pathlib import Path
from typing import Optional, Tuple
import os
import shutil
import traceback
from dataclasses import asdict, dataclass, field
from .worksheet_data import WorksheetData
from ..utils.user_utils import user_confirm
from ..generation.cs_generation import (
    begin_output_transaction,
    commit_output_transaction,
    discard_output_transaction,
    generate_enum_file_from_sheet,
    generate_enum_file,
    get_created_files,
    set_output_options,
    write_to_file,
)
from ..utils.log import log_info, log_warn, log_error, log_success, log_sep, green_filename, log_warn_summary
from ..exceptions import SheetNameConflictError, ExportError
from ..exceptions import InvalidFieldNameError
from ..exceptions import WriteFileError
from ..exceptions import DuplicateFieldError, HeaderFormatError, UnknownCustomTypeError
from ..generation.enum_registry import get_enum_registry, reset_enum_registry
from ..generation.stable_enum_values import STABLE_ENUM_VALUES_FILENAME, StableEnumValueAllocator
from ..utils.naming_config import ENUM_KEYS_SUFFIX, JSON_FILE_PATTERN
from ..utils.path_utils import discover_excel_files, is_excel_source_file
from ..hooks.runner import run_custom_hooks
REPORT = None  # 报表文件输出已移除
CS_ENUM_INT_MIN = -2147483648
CS_ENUM_INT_MAX = 2147483647
SHEETEASE_METADATA_DIR = ".sheetease"
STABLE_ENUM_VALUES_PROJECT_FILENAME = "stable_enum_values.json"
CONFIG_MANIFEST_FILENAME = "ConfigManifest.json"
GENERATED_CONFIG_CATALOG_FILENAME = "GeneratedConfigCatalog.cs"
TABLE_PROFILES_FILENAME = "table_profiles.json"


def _display_excel_path(excel_path: Path, source_folder: str) -> str:
    """返回带相对目录的 Excel 来源路径，避免同名文件在报错中无法区分。"""
    try:
        return excel_path.resolve().relative_to(Path(source_folder).resolve()).as_posix()
    except (OSError, ValueError):
        return str(excel_path.resolve())


@dataclass(frozen=True)
class ExportSummary:
    """一次完整导出或检查的机器可读摘要。"""

    excel_files: int
    eligible_files: int
    processed_files: int
    skipped_files: int
    generated_files: tuple[str, ...]
    generated_json_bytes: int
    duration_seconds: float
    diff_only: bool
    dry_run: bool
    hook_issues: tuple[dict, ...] = field(default_factory=tuple)
    formula_cells: int = 0
    formula_cache_missing: int = 0

    def to_dict(self) -> dict:
        """转换为可直接写入 JSON 的字典。"""
        return asdict(self)


def _validate_formula_cache(excel_path: Path, data_workbook) -> int:
    """校验主表导出区域的公式缓存，返回公式单元格数量。"""
    formula_workbook = None
    try:
        formula_workbook = openpyxl.load_workbook(str(excel_path), data_only=False)
        formula_sheet = formula_workbook.worksheets[0]
        data_sheet = data_workbook.worksheets[0]
        calculation = getattr(formula_workbook, "calculation", None)
        calculation_mode = getattr(calculation, "calcMode", None)
        if calculation_mode == "manual":
            log_warn(f"[{excel_path.name}] 工作簿计算模式为 manual；保存前请确认 Excel 已完成重新计算")

        formula_count = 0
        missing_cells: list[str] = []
        for row in formula_sheet.iter_rows(min_row=7, min_col=2):
            for formula_cell in row:
                if formula_cell.data_type != "f":
                    continue
                formula_count += 1
                if data_sheet[formula_cell.coordinate].value is None:
                    missing_cells.append(formula_cell.coordinate)
        if missing_cells:
            sample = ", ".join(missing_cells[:10])
            suffix = "" if len(missing_cells) <= 10 else f" 等共 {len(missing_cells)} 处"
            raise ExportError(
                f"{excel_path.name} 存在未缓存计算结果的公式单元格: {sample}{suffix}。"
                "请用 Excel 打开并完整重算、保存后再导出。"
            )
        if formula_count:
            log_info(f"[{excel_path.name}] 公式缓存校验通过: {formula_count} 个公式单元格")
        return formula_count
    finally:
        if formula_workbook is not None:
            formula_workbook.close()


def _build_config_manifest(sheets: list[WorksheetData], table_profiles: Optional[dict] = None) -> str:
    """构建独立配置清单；每表 JSON 本身不再混入工具元数据。"""
    profiles = table_profiles or {}
    tables = {}
    for sheet in sorted(sheets, key=lambda item: item.name):
        content = sheet._export_json_content or "{}"
        metadata = sheet.export_metadata
        tables[sheet.name] = {
            "file": JSON_FILE_PATTERN.format(name=sheet.name),
            "source_file": metadata.get("source_file"),
            "row_count": len(sheet.export_data or {}),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "fields": metadata.get("fields", {}),
            "load_mode": str(profiles.get(sheet.name, {}).get("load", "preload")),
        }
    return json.dumps({"schema_version": 1, "tables": tables}, ensure_ascii=False, indent=2)


def _build_generated_config_catalog(sheets: list[WorksheetData], table_profiles: Optional[dict] = None) -> str:
    """生成无反射的配置类型目录和构造工厂。"""
    profiles = table_profiles or {}
    entries = []
    mode_names = {"preload": "Preload", "lazy": "Lazy", "editorOnly": "EditorOnly", "editoronly": "EditorOnly"}
    for sheet in sorted(sheets, key=lambda item: item.name):
        raw_mode = str(profiles.get(sheet.name, {}).get("load", "preload"))
        if raw_mode not in mode_names:
            raise ExportError(f"表 {sheet.name} 的 load 策略无效: {raw_mode}，只允许 preload/lazy/editorOnly")
        mode = mode_names[raw_mode]
        entries.append(
            f'            new ConfigTableDescriptor(typeof({sheet.name}Info), typeof({sheet.name}Config), '
            f'"{sheet.name}Config", () => new {sheet.name}Config(), ConfigLoadMode.{mode}),'
        )
    body = "\n".join(entries)
    return (
        "// This is auto-generated, don't modify manually\n"
        "namespace Data.TableScript\n{\n"
        "    internal static class GeneratedConfigCatalog\n    {\n"
        "        internal static ConfigTableDescriptor[] CreateDescriptors()\n        {\n"
        "            return new[]\n            {\n"
        f"{body}\n"
        "            };\n        }\n    }\n}\n"
    )


def _resolve_table_profiles(source_folder: str, configured_profiles: Optional[dict]) -> dict:
    """读取可随 Excel 目录版本管理的表级策略；显式配置优先。"""
    if configured_profiles is not None:
        if not isinstance(configured_profiles, dict):
            raise ExportError("table_profiles 必须是 JSON 对象")
        return configured_profiles
    profile_path = Path(source_folder) / TABLE_PROFILES_FILENAME
    if not profile_path.is_file():
        return {}
    try:
        profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportError(f"无法读取表级加载策略 {profile_path}: {exc}") from exc
    if not isinstance(profiles, dict):
        raise ExportError(f"表级加载策略 {profile_path} 的根节点必须是 JSON 对象")
    return profiles


def _parse_manual_enum_value(raw_value, excel_name: str, sheet_name: str, row_index: int, item_name: str) -> Optional[int]:
    """Parse an optional C# enum int value from an Enum-* worksheet cell."""
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        value_text = raw_value.strip()
        if value_text == "":
            return None
        if not value_text.lstrip("+-").isdigit():
            raise ExportError(
                f"invalid enum value in {excel_name}/{sheet_name} row {row_index}: "
                f"{item_name}={raw_value!r}. Expected an integer in C# int range."
            )
        value = int(value_text)
    elif isinstance(raw_value, bool):
        raise ExportError(
            f"invalid enum value in {excel_name}/{sheet_name} row {row_index}: "
            f"{item_name}={raw_value!r}. Boolean is not a valid C# enum integer value."
        )
    elif isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float) and raw_value.is_integer():
        value = int(raw_value)
    else:
        raise ExportError(
            f"invalid enum value in {excel_name}/{sheet_name} row {row_index}: "
            f"{item_name}={raw_value!r}. Expected an integer in C# int range."
        )

    if value < CS_ENUM_INT_MIN or value > CS_ENUM_INT_MAX:
        raise ExportError(
            f"invalid enum value in {excel_name}/{sheet_name} row {row_index}: "
            f"{item_name}={value}. C# enum values must be in int range "
            f"[{CS_ENUM_INT_MIN}, {CS_ENUM_INT_MAX}]."
        )
    return value


def _next_csharp_enum_value(previous_value: Optional[int], excel_name: str, sheet_name: str, row_index: int, item_name: str) -> int:
    value = 0 if previous_value is None else previous_value + 1
    if value < CS_ENUM_INT_MIN or value > CS_ENUM_INT_MAX:
        raise ExportError(
            f"invalid enum value in {excel_name}/{sheet_name} row {row_index}: "
            f"{item_name} would be assigned {value} by C# default enum rules, "
            f"outside int range [{CS_ENUM_INT_MIN}, {CS_ENUM_INT_MAX}]."
        )
    return value


def _pick_primary_key_col_index(sheet) -> int:
    """推断主键所在列索引（0-based），优先兼容当前模板的 B 列。"""
    try:
        field_row = sheet[5]  # 第5行：字段名行
    except Exception:
        field_row = []

    def _has_value(cell) -> bool:
        if cell is None:
            return False
        val = cell.value
        if val is None:
            return False
        return str(val).strip() != ""

    # 当前导表约定：数据从 B 列开始；若 B 列字段存在，优先选择 B 列。
    if len(field_row) > 1 and _has_value(field_row[1]):
        return 1
    # 兼容旧模板：若 B 列不可用，回退到 A 列。
    if len(field_row) > 0 and _has_value(field_row[0]):
        return 0

    # 兜底：尝试读取类型行。若 B 列有类型定义则使用 B。
    try:
        type_row = sheet[3]  # 第3行：类型行
        if len(type_row) > 1 and _has_value(type_row[1]):
            return 1
    except Exception:
        pass
    return 0


def _stable_enum_manifest_path(
    source_folder: str,
    output_project_folder: Optional[str],
    output_client_folder: Optional[str],
) -> Path:
    """选择稳定枚举值 manifest 位置，优先放在 JSON 导出目录的工具元数据目录。"""
    if output_project_folder:
        return Path(output_project_folder) / SHEETEASE_METADATA_DIR / STABLE_ENUM_VALUES_PROJECT_FILENAME
    if output_client_folder:
        return Path(output_client_folder) / SHEETEASE_METADATA_DIR / STABLE_ENUM_VALUES_PROJECT_FILENAME
    return Path(source_folder) / STABLE_ENUM_VALUES_FILENAME


def process_excel_file(
    excel_path: Path,
    file_sheet_map: dict[str, str],
    output_client_folder: Optional[str],
    output_project_folder: Optional[str],
    csfile_output_folder: Optional[str],
    enum_output_folder: Optional[str],
    workbook=None,
    defer_outputs: bool = False,
) -> Optional[WorksheetData]:
    """
    处理单个Excel文件，生成JSON和C#代码。
    
    Args:
        excel_path: Excel文件路径
        file_sheet_map: 文件名到sheet名的映射（用于检测冲突）
        output_client_folder: 客户端JSON输出目录（可选）
        output_project_folder: 工程JSON输出目录（可选）
        csfile_output_folder: C#脚本输出目录（可选）
        enum_output_folder: 枚举输出目录（可选）
    
    Returns:
        WorksheetData对象，如果处理失败则返回None
    
    Raises:
        SheetNameConflictError: Sheet名冲突
        ExportError: 导出错误
    """
    wb = workbook
    opened_here = False
    if wb is None:
        try:
            wb = openpyxl.load_workbook(str(excel_path), data_only=True)
            opened_here = True
        except Exception as e:
            log_error(f"打开失败: {green_filename(excel_path.name)} -> {e}")
            raise ExportError(
                f"Excel 文件无法打开: {excel_path.name} -> {e}",
                context={"file": excel_path.name},
            ) from e
    main_sheet = wb.worksheets[0]
    if main_sheet.title in file_sheet_map.values():
        dup = next(f for f, s in file_sheet_map.items() if s == main_sheet.title)
        raise SheetNameConflictError(main_sheet.title, dup, excel_path.name)

    log_sep(f"开始 {green_filename(excel_path.name)}")
    main_sheet_data = WorksheetData(main_sheet)
    # 记录来源 Excel 文件名，供日志使用
    try:
        setattr(main_sheet_data, "source_file", excel_path.name)
    except Exception:
        pass

    if defer_outputs:
        main_sheet_data.build_export_data()
    else:
        if output_client_folder:
            main_sheet_data.generate_json(output_client_folder)
        if output_project_folder:
            main_sheet_data.generate_json(output_project_folder)
        if csfile_output_folder:
            main_sheet_data.generate_script(csfile_output_folder)

    # 注意：枚举导出已在第一阶段完成，这里不再重复导出

    file_sheet_map[excel_path.name] = main_sheet.title
    action = "解析完成" if defer_outputs else "完成"
    log_info(f"{action} {excel_path.name} \n")
    if opened_here:
        try:
            wb.close()
        except Exception:
            pass
    return main_sheet_data

def cleanup_files(output_folders: list[Optional[str]]) -> None:
    """
    清理输出目录中未在本次生成中出现的文件。
    
    Args:
        output_folders: 输出目录列表，None值会被忽略
    """
    created = set(get_created_files())
    from pathlib import Path
    stale = []
    for folder in filter(None, output_folders):
        p = Path(folder)
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if SHEETEASE_METADATA_DIR in f.relative_to(p).parts:
                continue
            if f.is_file() and f.suffix != ".meta":
                if str(f.resolve()) not in created and str(f.with_suffix(f.suffix + ".meta").resolve()) not in created:
                    stale.append(f)
    if not stale:
        log_info("没有需要删除的文件")
        return
    # 临时切换 warning 为立即输出
    log_warn("以下文件未在本次生成中出现：", immediate=True)
    for f in stale:
        log_warn(f" - {f}", immediate=True)
    msg = "是否删除这些文件?(y/n): "
    if user_confirm(msg, title="文件删除确认"):
        for f in stale:
            try:
                f.unlink(missing_ok=True)
                log_info(f"删除: {f}")
            except Exception as e:
                log_error(f"删除失败 {f}: {e}")
    else:
        log_warn("已取消清理")

def batch_excel_to_json(
    source_folder: str,
    output_client_folder: Optional[str] = None,
    output_project_folder: Optional[str] = None,
    csfile_output_folder: Optional[str] = None,
    enum_output_folder: Optional[str] = None,
    diff_only: bool = True,
    dry_run: bool = False,
    auto_cleanup: bool = True,
    hook_root: Optional[str] = None,
    table_profiles: Optional[dict] = None,
) -> ExportSummary:
    """
    批量处理Excel文件，生成JSON和C#代码。
    
    流程分为两个阶段：
    1. 第一阶段：收集并导出所有枚举
    2. 第二阶段：处理表格数据，生成JSON和C#脚本
    
    Args:
        source_folder: Excel文件源目录
        output_client_folder: 客户端JSON输出目录（可选）
        output_project_folder: 工程JSON输出目录（可选）
        csfile_output_folder: C#脚本输出目录（可选）
        enum_output_folder: 枚举输出目录（可选）
        diff_only: 是否仅在有差异时写入文件
        dry_run: 是否为试运行模式（不实际写入文件）
        auto_cleanup: 是否自动清理未使用的文件
        hook_root: 可选的工程自定义检查钩子目录；为空时不运行自定义检查
        table_profiles: 可选的表级加载策略，默认 preload
    
    Raises:
        ExportError: 导出过程中的各种错误
    """
    start = time.time()
    log_sep("开始导表")
    log_info(f"Excel目录: {source_folder}")
    set_output_options(diff_only=diff_only, dry_run=dry_run)
    table_profiles = _resolve_table_profiles(source_folder, table_profiles)

    # 输出目录可写性与磁盘空间检查
    def _check_output_dir(folder: Optional[str]) -> None:
        if not folder:
            return
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            raise ExportError(f"无法创建输出目录: {folder} -> {e}")
        # 检查是否可写
        if not os.access(folder, os.W_OK):
            raise ExportError(f"输出目录不可写: {folder}")
        # 检查剩余空间（简单策略：至少 10MB 可用）
        try:
            stat = os.statvfs(folder)
            free = stat.f_bavail * stat.f_frsize
            if free < 10 * 1024 * 1024:
                raise ExportError(f"输出目录磁盘空间不足 (<10MB): {folder}")
        except AttributeError:
            # Windows 不支持 statvfs，尝试使用 shutil.disk_usage
            try:
                du = shutil.disk_usage(folder)
                if du.free < 10 * 1024 * 1024:
                    raise ExportError(f"输出目录磁盘空间不足 (<10MB): {folder}")
            except Exception:
                pass

    import shutil
    _check_output_dir(output_client_folder)
    _check_output_dir(output_project_folder)
    _check_output_dir(csfile_output_folder)
    _check_output_dir(enum_output_folder)

    skip = 0
    ok = 0
    file_sheet_map: dict[str, str] = {}
    # 反查 map: sheet 名 -> excel 文件名（用于日志显示目标 Excel 文件）
    sheet_to_file_map: dict[str, str] = {}
    excel_files = discover_excel_files(Path(source_folder))
    eligible_files = [
        path for path in excel_files
        if is_excel_source_file(path)
    ]
    workbook_cache: dict[Path, object] = {}
    formula_cell_count = 0

    if not excel_files:
        log_warn("未找到 .xlsx 文件")

    # ========== 第一阶段：收集并导出所有枚举 ==========
    log_sep("第一阶段：收集并导出枚举")
    reset_enum_registry()  # 重置枚举注册表
    enum_registry = get_enum_registry()
    stable_enum_allocator = StableEnumValueAllocator(
        _stable_enum_manifest_path(source_folder, output_project_folder, output_client_folder),
        bootstrap_dirs=[
            Path(csfile_output_folder) if csfile_output_folder else None,
            Path(enum_output_folder) if enum_output_folder else None,
        ],
    )
    
    # 收集所有需要导出的枚举
    enum_files_to_export: list[Tuple[Path, str, list, list]] = []  # (excel_path, enum_type_name, enum_data, remarks)
    
    for excel_path in excel_files:
        excel_source = _display_excel_path(excel_path, source_folder)
        if not excel_path.name[0].isupper():
            continue
        
        try:
            wb = openpyxl.load_workbook(str(excel_path), data_only=True)
        except Exception as e:
            log_error(f"打开失败（枚举收集阶段）: {green_filename(excel_path.name)} -> {e}")
            continue
        workbook_cache[excel_path] = wb
        
        main_sheet = wb.worksheets[0]
        
        # 方式1：检查主键是否为string类型（需要生成枚举）
        try:
            # 读取类型行（第3行），并按模板推断主键列
            pk_col_index = _pick_primary_key_col_index(main_sheet)
            if len(main_sheet[3]) > pk_col_index:
                type_cell = main_sheet[3][pk_col_index]
                first_field_type = str(type_cell.value).strip().lower() if type_cell.value else ""
                if first_field_type in ("str", "string"):
                    # 需要生成枚举，收集枚举项（从第7行开始）
                    enum_type_name = f"{main_sheet.title}{ENUM_KEYS_SUFFIX}"
                    enum_names = []
                    enum_explicit_values = {}
                    enum_default_values = {}
                    enum_remarks = []  # 收集注释（来自第1行备注列）
                    idx_val = 0
                    for row in main_sheet.iter_rows(
                        min_row=7,
                        min_col=pk_col_index + 1,
                        max_col=pk_col_index + 1,
                        values_only=False,
                    ):
                        if not row or not row[0]:
                            continue
                        val = row[0].value
                        if val is None:
                            continue
                        val_str = str(val).strip()
                        if val_str:
                            enum_names.append(val_str)
                            enum_explicit_values[val_str] = None
                            enum_default_values[val_str] = idx_val
                            # 收集注释：第1行（备注行）对应列的值
                            remark = None
                            if len(main_sheet[1]) > pk_col_index:  # 第1行存在对应列
                                remark_cell = main_sheet[1][pk_col_index]  # 与主键列对齐
                                if remark_cell and remark_cell.value:
                                    remark = str(remark_cell.value).strip()
                                    if not remark:
                                        remark = None
                            enum_remarks.append(remark)
                            idx_val += 1
                    
                    if enum_names:
                        # 验证枚举项名称格式
                        invalid_items = []
                        for item_name in enum_names:
                            if not enum_registry.validate_enum_item_name(item_name, require_pascal_case=False):
                                invalid_items.append(item_name)
                        if invalid_items:
                            raise ExportError(
                                f"枚举 {enum_type_name} (来自 {excel_source}) 包含不符合C#标识符规范的枚举项: {invalid_items}。"
                                f"自动生成的 Keys 枚举允许小写/下划线，但仍必须是合法 C# 标识符"
                            )
                        enum_items = stable_enum_allocator.allocate(
                            enum_type_name,
                            enum_names,
                            enum_explicit_values,
                            enum_default_values,
                            f"{excel_source} (主键为string类型)",
                        )
                        # 注册枚举，记录来源信息
                        source_info = f"{excel_source} (主键为string类型)"
                        enum_registry.register_enum(
                            enum_type_name,
                            enum_items,
                            "Data.TableScript",
                            source_info,
                            require_pascal_case_items=False,
                        )
                        # 自动 Keys 枚举保持原有导出策略：由 worksheet_data.generate_script 负责输出，
                        # 第一阶段仅注册到运行时注册表，不再额外导出到 enum_output_folder，避免重复产物。
                        log_info(f"收集枚举(仅注册，不导出文件): {enum_type_name} (来自 {excel_source})")
        except ExportError as e:
            # 枚举相关的错误直接抛出，中断导表
            log_error(f"枚举收集失败: {e}")
            raise
        except Exception as e:
            log_warn(f"收集枚举时出错 {excel_path.name}: {e}")
        
        # 方式2：检查是否有Enum-开头的sheet
        try:
            if len(wb.worksheets) > 1 and enum_output_folder:
                enum_tag = "Enum-"
                for sheet in wb.worksheets[1:]:
                    if sheet.title.startswith(enum_tag):
                        enum_type_name = sheet.title.replace(enum_tag, "")
                        enum_names = []
                        enum_explicit_values = {}
                        enum_default_values = {}
                        enum_remarks = []  # 收集注释（来自第3列）
                        rows = list(sheet.iter_rows(min_row=2))
                        previous_effective_value = None
                        for row_index, r in enumerate(rows, start=2):
                            if len(r) < 1:
                                continue
                            name = r[0].value
                            val = r[1].value if len(r) > 1 else None
                            if name is None:
                                continue
                            name_str = str(name).strip()
                            if not name_str:
                                continue
                            if name_str in enum_names:
                                raise ExportError(
                                    f"duplicate enum item in {excel_source}/{sheet.title} row {row_index}: "
                                    f"{name_str}. C# enum member names must be unique."
                                )

                            explicit_value = _parse_manual_enum_value(
                                val,
                                excel_path.name,
                                sheet.title,
                                row_index,
                                name_str,
                            )
                            default_value = (
                                explicit_value
                                if explicit_value is not None
                                else _next_csharp_enum_value(
                                    previous_effective_value,
                                    excel_path.name,
                                    sheet.title,
                                    row_index,
                                    name_str,
                                )
                            )
                            previous_effective_value = default_value

                            enum_names.append(name_str)
                            enum_explicit_values[name_str] = explicit_value
                            enum_default_values[name_str] = default_value
                            # 收集注释：第3列（索引2）
                            remark = None
                            if len(r) > 2 and r[2].value:
                                remark = str(r[2].value).strip()
                                if not remark:
                                    remark = None
                            enum_remarks.append(remark)
                        
                        if enum_names:
                            # 验证枚举项名称格式
                            invalid_items = []
                            for item_name in enum_names:
                                if not enum_registry.validate_enum_item_name(item_name):
                                    invalid_items.append(item_name)
                            if invalid_items:
                                raise ExportError(
                                    f"枚举 {enum_type_name} (来自 {excel_source}/{sheet.title}) 包含不符合C#命名规范的枚举项: {invalid_items}。"
                                    f"枚举项必须以大写字母开头（大写驼峰式）"
                                )
                            enum_items = stable_enum_allocator.allocate(
                                enum_type_name,
                                enum_names,
                                enum_explicit_values,
                                enum_default_values,
                                f"{excel_source}/{sheet.title}",
                            )
                            # 注册枚举，记录来源信息
                            source_info = f"{excel_source}/{sheet.title}"
                            enum_registry.register_enum(enum_type_name, enum_items, "Data.TableScript", source_info)
                            enum_files_to_export.append((excel_path, enum_type_name, list(enum_items.items()), enum_remarks))
                            log_info(f"收集枚举: {enum_type_name} (来自 {excel_source}/{sheet.title})")
        except ExportError as e:
            # 枚举相关的错误直接抛出，中断导表
            log_error(f"枚举收集失败: {e}")
            raise
        except Exception as e:
            log_warn(f"收集枚举时出错（方式2）{excel_path.name}: {e}")
        
        # workbook 延迟到第二阶段后统一关闭，避免重复加载

    # ========== 第二阶段：处理表格数据 ==========
    log_sep("第二阶段：处理表格数据")
    sheets: list[WorksheetData] = []
    aborted = False
    try:
        for excel_path in excel_files:
            if not excel_path.name[0].isupper():
                log_warn(f"跳过(首字母非大写): {green_filename(excel_path.name)}")
                skip += 1
                continue
            try:
                formula_cell_count += _validate_formula_cache(excel_path, workbook_cache.get(excel_path))
                ws = process_excel_file(
                    excel_path,
                    file_sheet_map,
                    output_client_folder,
                    output_project_folder,
                    csfile_output_folder,
                    enum_output_folder,
                    workbook=workbook_cache.get(excel_path),
                    defer_outputs=True,
                )
                if ws is not None:
                    sheets.append(ws)
                    # 记录 sheet -> 文件名
                    try:
                        sheet_to_file_map[ws.name] = excel_path.name
                    except Exception:
                        pass
                ok += 1
            except Exception as e:
                # 所有异常视为致命：打印红色错误、堆栈信息，并抛出给上层处理
                tb = traceback.format_exc()
                log_error(f"{excel_path.name} 失败: {e}\n{tb}")
                raise ExportError(f"{excel_path.name} 处理失败: {e}") from e
    finally:
        # 第二阶段结束后关闭缓存的 workbook
        for wb in workbook_cache.values():
            try:
                wb.close()
            except Exception:
                pass

    # ========== 第三阶段：工程自定义检查 ==========
    # 不配置钩子目录时完全跳过；配置后，任何 error 都会在实际文件写入前中断导出。
    hook_issues = []
    if hook_root and str(hook_root).strip():
        hook_issues = run_custom_hooks(
            str(hook_root).strip(),
            sheets,
            source_folder,
            config={
                "source_folder": source_folder,
                "output_client_folder": output_client_folder,
                "output_project_folder": output_project_folder,
                "csfile_output_folder": csfile_output_folder,
                "enum_output_folder": enum_output_folder,
                "diff_only": diff_only,
                "dry_run": dry_run,
            },
        )

    # ========== 第四阶段：引用检查 ==========
    # 必须使用本轮内存模型；dry-run 也不再读取可能过期的旧 JSON。
    export_data_by_sheet = {
        ws.name: ws.export_data if ws.export_data is not None else ws.build_export_data()
        for ws in sheets
    }
    reference_error_count = 0
    if sheets:
        log_sep("引用检查")
        search_dirs = [output_client_folder, output_project_folder]
        for ws in sheets:
            reference_error_count += ws.run_reference_checks(
                search_dirs,
                sheet_to_file_map,
                export_data_by_sheet,
            )
    if reference_error_count:
        raise ExportError(f"引用检查失败，共发现 {reference_error_count} 个错误；未写入任何导出产物")

    # ========== 第五阶段：检查通过后写入产物 ==========
    log_sep("写入导出产物")
    begin_output_transaction()

    if enum_output_folder and enum_files_to_export:
        enum_names_seen = {}
        for excel_path, enum_type_name, enum_data, remarks in enum_files_to_export:
            excel_source = _display_excel_path(excel_path, source_folder)
            if enum_type_name in enum_names_seen:
                existing_source = enum_names_seen[enum_type_name]
                raise ExportError(
                    f"发现重复的枚举定义: {enum_type_name}\n"
                    f"已有定义（来源: {existing_source}）\n"
                    f"重复定义（来源: {excel_source}）\n"
                    f"任何情况下都不应该导出两个相同的枚举。"
                )
            enum_names_seen[enum_type_name] = excel_source

        log_info(f"开始导出 {len(enum_files_to_export)} 个枚举...")
        for excel_path, enum_type_name, enum_data, remarks in enum_files_to_export:
            enum_names = [item[0] for item in enum_data]
            enum_values = [item[1] for item in enum_data]
            generate_enum_file(enum_type_name, enum_names, enum_values, remarks, "Data.TableScript", enum_output_folder)
            log_info(f"已导出枚举: {enum_type_name}")
    elif enum_output_folder:
        log_info("未发现需要导出的枚举")

    for ws in sheets:
        if output_client_folder:
            ws.write_json(output_client_folder)
        if output_project_folder:
            ws.write_json(output_project_folder)
        if csfile_output_folder:
            ws.generate_script(csfile_output_folder)

    if csfile_output_folder:
        write_to_file(
            _build_generated_config_catalog(sheets, table_profiles),
            os.path.join(csfile_output_folder, GENERATED_CONFIG_CATALOG_FILENAME),
        )

    manifest_content = _build_config_manifest(sheets, table_profiles)
    if output_client_folder:
        write_to_file(manifest_content, os.path.join(output_client_folder, CONFIG_MANIFEST_FILENAME))
    if output_project_folder:
        write_to_file(manifest_content, os.path.join(output_project_folder, CONFIG_MANIFEST_FILENAME))

    try:
        commit_output_transaction()
        if not dry_run:
            stable_enum_allocator.save()
    except Exception:
        discard_output_transaction()
        raise

    # 打印每表错误/警告统计（若实现了内部统计则输出；当前由 worksheet 在控制台输出具体错误）

    if auto_cleanup and not aborted:
        log_sep("清理阶段")
        cleanup_files([output_client_folder, output_project_folder, csfile_output_folder, enum_output_folder])

    elapsed = time.time() - start
    log_sep("结束")
    # 统计本次生成的 JSON 文件总体积（仅统计已实际写入的文件）
    try:
        created_files = set(get_created_files())
        total_json_bytes = 0
        for p in created_files:
            try:
                if p.lower().endswith('.json') and os.path.isfile(p):
                    total_json_bytes += os.path.getsize(p)
            except Exception:
                # 忽略单个文件统计失败
                pass

        def _human_bytes(n: int) -> str:
            # 简单的人类可读格式
            if n < 1024:
                return f"{n} B"
            if n < 1024 * 1024:
                return f"{n/1024:.1f} KB"
            return f"{n/1024/1024:.2f} MB"

        total_json_str = _human_bytes(total_json_bytes)
    except Exception:
        total_json_bytes = 0
        total_json_str = "N/A"

    # 在打印最终结果前统一输出所有警告，便于快速查看
    try:
        log_warn_summary("以下为本次运行收集到的所有警告：")
    except Exception:
        pass
    if aborted:
        log_error(f"导表已中止: 字段命名不合法，已停止后续处理。成功 {ok}，跳过 {skip}，总耗时 {elapsed:.2f}s，总生成 JSON 大小: {total_json_str}")
    else:
        log_success(f"成功 {ok}，跳过 {skip}，总耗时 {elapsed:.2f}s，总生成 JSON 大小: {total_json_str}. diff_only:{diff_only}, dry_run:{dry_run}")

    return ExportSummary(
        excel_files=len(excel_files),
        eligible_files=len(eligible_files),
        processed_files=ok,
        skipped_files=skip,
        generated_files=tuple(sorted(set(get_created_files()))),
        generated_json_bytes=total_json_bytes,
        duration_seconds=round(elapsed, 6),
        diff_only=diff_only,
        dry_run=dry_run,
        hook_issues=tuple(asdict(issue) for issue in hook_issues),
        formula_cells=formula_cell_count,
        formula_cache_missing=0,
    )
