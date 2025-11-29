# Author: huhongwei 306463233@qq.com
# MIT License
import os
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Optional, List, Iterable, Tuple
from .log import log_warn, log_info
from .naming_config import CS_FILE_SUFFIX
from .type_utils import convert_type_to_csharp

# ================== 常量与内部配置（不改变原有输出格式） ==================
# CONST 区域：集中所有内部可调开关，方便阅读与维护
_ENUM_DUP_CHECK = True                # 是否进行枚举名称重复检测（仅日志）
_ENUM_REQUIRE_VALUE = False           # 若要求枚举值必须是 int，可改为 True（当前保持 False）
_DIFF_ONLY = True                     # 内容不变不重写
_DRY_RUN = False                      # 试运行不开写
_created_files: List[str] = []        # 已生成文件记录
# ========================================================================

def set_output_options(diff_only: bool = True, dry_run: bool = False) -> None:
    """设置是否仅在内容变化时写入(diff) 与是否试运行(dry-run)"""
    global _DIFF_ONLY, _DRY_RUN
    _DIFF_ONLY = diff_only
    _DRY_RUN = dry_run

def get_created_files():
    """推荐使用的新命名（旧 get_create_files 仍兼容）"""
    return _created_files

def generate_xml_summary(origin_str: str) -> str:
    if origin_str is None:
        origin_str = ""
    lines = origin_str.splitlines()
    if len(lines) <= 1:
        return f"/// <summary> {origin_str} </summary>"
    body = "\n".join(f"/// {l}" for l in lines)
    return f"/// <summary>\n{body}\n/// </summary>"

auto_generated_summary_string = generate_xml_summary("This is auto-generated, don't modify manually")
enum_namespace = "ConfigDataName"
I_CONFIG_RAW_INFO_NAME = "IConfigRawInfo"

def generate_enum_file_from_sheet(sheet, enum_tag, output_folder):
    """
    由枚举工作表生成枚举文件：
    - 保持原逻辑与输出不变
    - 新增重复名称检测日志（不影响生成）
    - 新增：若 _ENUM_REQUIRE_VALUE=True 则校验枚举值是否为 int，否则发出警告
    """
    rows = list(sheet.iter_rows(min_row=2))
    if not rows:
        log_warn(f"枚举表空: {sheet.title}")
        return
    enum_type_name = sheet.title.replace(enum_tag, "")
    enum_names, enum_values, remarks = [], [], []
    name_seen = set()
    dup_names = set()
    for r in rows:
        if len(r) < 2:
            continue
        name = r[0].value
        val = r[1].value
        remark = r[2].value if len(r) > 2 else None
        if name is None or val is None:
            log_warn(f"{sheet.title} 跳过一行（缺 name 或 value）")
            continue
        if _ENUM_DUP_CHECK:
            if name in name_seen:
                dup_names.add(name)
            else:
                name_seen.add(name)
        if _ENUM_REQUIRE_VALUE and not isinstance(val, int):
            log_warn(f"{sheet.title} 枚举值非 int: {name}={val}")
        enum_names.append(name)
        enum_values.append(val)
        remarks.append(remark)
    if not enum_names:
        log_warn(f"{sheet.title} 没有有效枚举项")
        return
    if dup_names:
        log_warn(f"{sheet.title} 存在重复枚举名: {sorted(dup_names)}")
    generate_enum_file(enum_type_name, enum_names, enum_values, remarks, enum_namespace, output_folder)

def _build_enum_source(enum_type_name: str,
                       enum_names: List[str],
                       enum_values: List[str],
                       remarks: Optional[List[str]],
                       name_space: str) -> str:
    """
    构建枚举 C# 源码字符串（拆分函数提高可读性，不改变输出）
    """
    file_content = (
        f"namespace {name_space}\n{{\n\t{auto_generated_summary_string}\n\tpublic enum {enum_type_name}\n\t{{\n"
    )
    for i, key in enumerate(enum_names):
        if remarks and remarks[i]:
            file_content += f'\t\t{generate_xml_summary(str(remarks[i]))}\n'
        file_content += f'\t\t{key} = {enum_values[i]},\n\n'
    file_content += "\t}\n}"
    return file_content

def generate_enum_file(enum_type_name, enum_names, enum_values, remarks, name_space, output_folder):
    # 使用内部构建函数
    file_content = _build_enum_source(enum_type_name, enum_names, enum_values, remarks, name_space)
    cs_file_path = os.path.join(output_folder, f"{enum_type_name}.cs")
    write_to_file(file_content, cs_file_path)

USING_NAMESPACE_STR = "\n".join([
    "using System.Collections.Generic;",
    "using Newtonsoft.Json;",
    "\n\n",
])
NAMESPACE_WRAPPER_STR = "namespace Data.TableScript\n{{\n{0}\n}}"

def add_indentation(input_str, indent="\t"):
    # 性能微调：局部变量绑定 & 列表推导
    lines = input_str.splitlines()
    return "\n".join([indent + line for line in lines])



def wrap_class_str(class_name, class_content_str, interface_name=""):
    """
    生成类代码块。
    说明：即使内容为空也保持包裹结构与缩进（空内容仍会经过 add_indentation 处理），
    以确保格式与历史输出一致，避免产生不必要 diff。
    """
    interface_part = f" : {interface_name}" if interface_name else ""
    indented = add_indentation(class_content_str) if class_content_str else add_indentation("")
    return f"public class {class_name}{interface_part}\n{{\n{indented}\n}}"

def generate_script_file(sheet_name: str,
                         properties_dict: Dict[str, str],
                         property_remarks: Dict[str, str],
                         output_folder: str,
                         need_generate_keys: bool = False,
                         file_suffix: str = CS_FILE_SUFFIX,
                         composite_keys: bool = False,
                         composite_multiplier: int = 46340,
                         composite_key_fields: Optional[Dict[str, str]] = None):
    """
    生成主脚本文件：
    """
    info_class = f"{auto_generated_summary_string}\n{generate_info_class(sheet_name, properties_dict, property_remarks)}"
    data_class = f"{generate_data_class(sheet_name, need_generate_keys, composite_keys, composite_multiplier)}"
    # 两块之间保持一个空行
    file_content = f"{info_class}\n\n{data_class}"
    final_content = USING_NAMESPACE_STR + NAMESPACE_WRAPPER_STR.format(add_indentation(file_content))
    cs_file_path = os.path.join(output_folder, f"{sheet_name}{file_suffix}.cs")
    write_to_file(final_content, cs_file_path)

def generate_info_class(class_name, properties_dict, property_remarks):
    """
    生成 Info 类：
    - 自动补齐 id / name
    - 输出顺序保持原逻辑（字段插入顺序 -> dict 顺序）
    """
    property_access_decorator = "{ get; private set; }"
    converted: List[str] = []
    append = converted.append  # 局部绑定轻微性能提升
    for k, v in properties_dict.items():
        append(
            f"{generate_xml_summary(property_remarks[k])}\n"
            f"[JsonProperty(\"{k}\")]\n"
            f"public {convert_type_to_csharp(v)} {k} {property_access_decorator}"
        )
    if "id" not in properties_dict:
        log_warn(f"{class_name}Info 缺少 id，已自动补齐")
        append(
            f"{generate_xml_summary('Auto-added to satisfy IConfigRawInfo')}\n"
            "[JsonProperty(\"id\")]\npublic int id { get; private set; }"
        )
    if "name" not in properties_dict:
        log_warn(f"{class_name}Info 缺少 name，已自动补齐")
        append(
            f"{generate_xml_summary('Auto-added to satisfy IConfigRawInfo')}\n"
            "[JsonProperty(\"name\")]\npublic string name { get; private set; }"
        )
    return wrap_class_str(class_name + "Info", "\n\n".join(converted), interface_name=I_CONFIG_RAW_INFO_NAME)

def generate_data_class(sheet_name: str,
                        need_generate_keys: bool,
                        composite_keys: bool,
                        composite_multiplier: int):
    """
    生成 Config 数据类：
    - 注释保持当前 XML summary 形式
    """
    class_name = f"{sheet_name}Config"
    if need_generate_keys:
        base_class = f"ConfigDataWithKey<{sheet_name}Info, {sheet_name}Keys>"
    elif composite_keys:
        base_class = f"ConfigDataWithCompositeId<{sheet_name}Info>"
    else:
        base_class = f"ConfigDataBase<{sheet_name}Info>"
    parts: List[str] = []
    if composite_keys and not need_generate_keys:
        parts.append(f"protected override int CompositeMultiplier => {composite_multiplier};")
    body = "\n\n".join(parts)
    header = (
        f"/// <summary>\n"
        f"/// Config data class for {sheet_name}. Generated by tool.\n"
        f"/// Query methods are provided by ConfigManager; keep this class minimal.\n"
        f"/// </summary>"
    )
    return f"{header}\n{wrap_class_str(class_name, body, interface_name=base_class)}"

def _content_unchanged(path: Path, new_content: str) -> bool:
    """
    判断文件内容是否与新内容相同
    """
    try:
        old = path.read_text(encoding="utf-8")
        return old == new_content
    except Exception:
        return False

def write_to_file(content: str, file_path: str) -> None:
    """
    写文件：
    - 支持 dry-run
    - diff-only：内容相同则不覆写
    - 原子写入（临时文件 + move）
    - 记录创建文件列表
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if _DRY_RUN:
        log_info(f"[DryRun] 生成文件(未写入): {file_path}")
        _created_files.append(str(path.resolve()))
        return

    if _DIFF_ONLY and path.exists() and _content_unchanged(path, content):
        log_info(f"文件未变化: {file_path}")
        _created_files.append(str(path.resolve()))
        return

    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            shutil.move(tmp_name, path)
            log_info(f"成功生成文件: {file_path}")
            _created_files.append(str(path.resolve()))
        finally:
            # 若临时文件残留则尝试删除
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except Exception:
                    pass
    except Exception as e:
        # 将写入失败升级为异常，便于上层统一处理
        from .exceptions import WriteFileError
        raise WriteFileError(file_path, str(e))
