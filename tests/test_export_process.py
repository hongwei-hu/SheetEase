"""导表流程模块测试。"""

from pathlib import Path

import openpyxl
import pytest

from ExcelExportTool.core import export_process
from ExcelExportTool.exceptions import ExportError, SheetNameConflictError
from ExcelExportTool.generation.enum_registry import get_enum_registry, reset_enum_registry


def test_process_excel_file_sheet_name_conflict_raises():
    wb = openpyxl.Workbook()
    wb.active.title = "SameSheet"

    with pytest.raises(SheetNameConflictError):
        export_process.process_excel_file(
            excel_path=Path("B.xlsx"),
            file_sheet_map={"A.xlsx": "SameSheet"},
            output_client_folder=None,
            output_project_folder=None,
            csfile_output_folder=None,
            enum_output_folder=None,
            workbook=wb,
        )


def test_process_excel_file_calls_generate_methods(monkeypatch, tmp_path):
    class DummyWSData:
        def __init__(self, ws):
            self.name = ws.title
            self.generated_json = 0
            self.generated_script = 0

        def generate_json(self, output_folder):
            self.generated_json += 1

        def generate_script(self, output_folder):
            self.generated_script += 1

    wb = openpyxl.Workbook()
    wb.active.title = "Item"

    monkeypatch.setattr(export_process, "WorksheetData", DummyWSData)

    result = export_process.process_excel_file(
        excel_path=Path("Item.xlsx"),
        file_sheet_map={},
        output_client_folder=str(tmp_path / "client"),
        output_project_folder=str(tmp_path / "project"),
        csfile_output_folder=str(tmp_path / "cs"),
        enum_output_folder=None,
        workbook=wb,
    )

    assert result is not None
    assert result.generated_json == 2
    assert result.generated_script == 1


def test_batch_excel_to_json_warns_when_no_files(monkeypatch, tmp_path):
    warned = []
    monkeypatch.setattr(export_process, "log_warn", lambda msg, **kwargs: warned.append(msg))

    export_process.batch_excel_to_json(
        source_folder=str(tmp_path),
        output_client_folder=None,
        output_project_folder=None,
        csfile_output_folder=None,
        enum_output_folder=None,
        auto_cleanup=False,
    )

    assert any("未找到 .xlsx 文件" in m for m in warned)


def test_batch_excel_to_json_output_not_writable_raises(monkeypatch, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    original_access = export_process.os.access

    def fake_access(path, mode):
        if str(path) == str(out_dir):
            return False
        return original_access(path, mode)

    monkeypatch.setattr(export_process.os, "access", fake_access)

    with pytest.raises(ExportError, match="输出目录不可写"):
        export_process.batch_excel_to_json(
            source_folder=str(tmp_path),
            output_client_folder=None,
            output_project_folder=str(out_dir),
            csfile_output_folder=None,
            enum_output_folder=None,
            auto_cleanup=False,
        )


def _build_minimal_workbook_for_enum_collection(path: Path, type_col: int) -> None:
    """创建仅用于第一阶段枚举收集的最小工作簿。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = path.stem
    # 第3行：类型；第7行：第一条数据
    ws.cell(row=3, column=type_col, value="string")
    ws.cell(row=5, column=type_col, value="weapon_template")
    ws.cell(row=7, column=type_col, value="SwordTemplate")
    wb.save(path)
    wb.close()


def test_batch_excel_to_json_collects_keys_enum_from_column_b(monkeypatch, tmp_path):
    # 文件名首字母大写才会参与导表
    xlsx = tmp_path / "WeaponTemplate.xlsx"
    _build_minimal_workbook_for_enum_collection(xlsx, type_col=2)  # B列

    # 避免进入第二阶段复杂解析，专注验证第一阶段枚举收集
    monkeypatch.setattr(export_process, "process_excel_file", lambda *args, **kwargs: None)

    reset_enum_registry()
    export_process.batch_excel_to_json(
        source_folder=str(tmp_path),
        output_client_folder=None,
        output_project_folder=None,
        csfile_output_folder=None,
        enum_output_folder=None,
        auto_cleanup=False,
    )

    reg = get_enum_registry()
    assert reg.has_enum("WeaponTemplateKeys")
    assert reg.get_enum_value("WeaponTemplateKeys", "SwordTemplate") == 0


def test_batch_excel_to_json_collects_keys_enum_from_column_a_fallback(monkeypatch, tmp_path):
    xlsx = tmp_path / "LegacyTemplate.xlsx"
    _build_minimal_workbook_for_enum_collection(xlsx, type_col=1)  # A列（旧模板回退）

    monkeypatch.setattr(export_process, "process_excel_file", lambda *args, **kwargs: None)

    reset_enum_registry()
    export_process.batch_excel_to_json(
        source_folder=str(tmp_path),
        output_client_folder=None,
        output_project_folder=None,
        csfile_output_folder=None,
        enum_output_folder=None,
        auto_cleanup=False,
    )

    reg = get_enum_registry()
    assert reg.has_enum("LegacyTemplateKeys")
    assert reg.get_enum_value("LegacyTemplateKeys", "SwordTemplate") == 0


def test_batch_excel_to_json_does_not_export_auto_keys_to_enum_folder(monkeypatch, tmp_path):
    xlsx = tmp_path / "CombatAttribute.xlsx"
    _build_minimal_workbook_for_enum_collection(xlsx, type_col=2)  # B列 string 主键

    monkeypatch.setattr(export_process, "process_excel_file", lambda *args, **kwargs: None)

    exported_enum_names = []

    def _fake_generate_enum_file(enum_type_name, enum_names, enum_values, remarks, name_space, output_folder):
        exported_enum_names.append(enum_type_name)

    monkeypatch.setattr(export_process, "generate_enum_file", _fake_generate_enum_file)

    enum_out = tmp_path / "enum_out"
    enum_out.mkdir(parents=True, exist_ok=True)

    reset_enum_registry()
    export_process.batch_excel_to_json(
        source_folder=str(tmp_path),
        output_client_folder=None,
        output_project_folder=None,
        csfile_output_folder=None,
        enum_output_folder=str(enum_out),
        auto_cleanup=False,
    )

    # 自动 Keys 枚举只注册，不写入 enum_output_folder
    assert "CombatAttributeKeys" not in exported_enum_names

    # 但运行时注册表仍可用（供 Enum(...) 字段校验与转换）
    reg = get_enum_registry()
    assert reg.has_enum("CombatAttributeKeys")
