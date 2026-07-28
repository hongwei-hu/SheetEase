"""命令行自动化模式与报告契约测试。"""

import json
import io
from dataclasses import dataclass

from ExcelExportTool.core import export_all
from ExcelExportTool.exceptions import HookValidationError
from ExcelExportTool.hooks.models import HookIssue


@dataclass
class DummySummary:
    processed_files: int = 2

    def to_dict(self):
        return {"processed_files": self.processed_files}


def _valid_config():
    return {
        "excel_root": "D:/Excel",
        "output_project": "J:/Project/Assets/Json",
        "cs_output": "J:/Project/Assets/Cs",
        "enum_output": "J:/Project/Assets/Enum",
    }


def test_headless_success_writes_machine_readable_report(monkeypatch, tmp_path):
    config_path = tmp_path / "sheet_config.json"
    config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")
    report_path = tmp_path / "report.json"

    monkeypatch.setattr(export_all, "_strict_validate", lambda cfg, force_no_assets=False: (True, ""))
    monkeypatch.setattr(export_all, "batch_excel_to_json", lambda *args, **kwargs: DummySummary())

    code = export_all.main([
        "--headless",
        "--dry-run",
        "--no-cleanup",
        "--config",
        str(config_path),
        "--report",
        str(report_path),
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == export_all.EXIT_SUCCESS
    assert report["schema_version"] == 1
    assert report["mode"] == "check"
    assert report["status"] == "succeeded"
    assert report["summary"] == {"processed_files": 2}
    assert report["options"]["auto_cleanup"] is False


def test_headless_missing_config_does_not_open_gui_and_reports_config_error(tmp_path):
    report_path = tmp_path / "failed.json"

    code = export_all.main([
        "--headless",
        "--config",
        str(tmp_path / "missing.json"),
        "--report",
        str(report_path),
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == export_all.EXIT_CONFIG_ERROR
    assert report["status"] == "failed"
    assert report["error"]["type"] == "ConfigError"
    assert "无法读取配置文件" in report["error"]["message"]


def test_headless_rejects_non_object_config_as_config_error(tmp_path):
    config_path = tmp_path / "list-config.json"
    config_path.write_text("[]", encoding="utf-8")
    report_path = tmp_path / "failed.json"

    code = export_all.main([
        "--headless",
        "--config",
        str(config_path),
        "--report",
        str(report_path),
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == export_all.EXIT_CONFIG_ERROR
    assert "根节点必须是 JSON 对象" in report["error"]["message"]


def test_hook_failure_preserves_structured_issues(monkeypatch, tmp_path):
    config_path = tmp_path / "sheet_config.json"
    config_path.write_text(json.dumps(_valid_config()), encoding="utf-8")
    report_path = tmp_path / "hook-failed.json"
    issue = HookIssue(
        "error",
        "RG_TEST_RULE",
        "测试规则未通过",
        file="Item.xlsx",
        sheet="Item",
        row=8,
        field="price",
        suggestion="填写非负数",
    )

    monkeypatch.setattr(export_all, "_strict_validate", lambda cfg, force_no_assets=False: (True, ""))

    def fail_export(*args, **kwargs):
        raise HookValidationError("自定义检查未通过", [issue])

    monkeypatch.setattr(export_all, "batch_excel_to_json", fail_export)

    code = export_all.main([
        "--headless",
        "--config",
        str(config_path),
        "--report",
        str(report_path),
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == export_all.EXIT_EXPORT_ERROR
    assert report["error"]["issues"] == [{
        "severity": "error",
        "code": "RG_TEST_RULE",
        "message": "测试规则未通过",
        "file": "Item.xlsx",
        "sheet": "Item",
        "row": 8,
        "field": "price",
        "suggestion": "填写非负数",
    }]


def test_packaged_entry_only_switches_to_cli_for_explicit_headless():
    from ExcelExportTool import app_main

    assert app_main._is_headless_request(["--headless", "--config", "x.json"])
    assert not app_main._is_headless_request(["--config", "x.json"])


def test_log_tee_ignores_invalid_windowed_executable_stream():
    class InvalidStream:
        def write(self, text):
            raise OSError(22, "Invalid argument")

        def flush(self):
            raise OSError(22, "Invalid argument")

    capture = io.StringIO()
    stream = export_all.TeeTextIO(InvalidStream(), capture)

    assert stream.write("保留到报告") == len("保留到报告")
    stream.flush()
    assert capture.getvalue() == "保留到报告"
