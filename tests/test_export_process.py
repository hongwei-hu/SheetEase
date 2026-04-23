"""导表流程模块测试。"""

from pathlib import Path

import openpyxl
import pytest

from ExcelExportTool.core import export_process
from ExcelExportTool.exceptions import ExportError, SheetNameConflictError


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
