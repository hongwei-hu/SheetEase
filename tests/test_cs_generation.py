"""代码生成模块测试。"""

import os

import pytest

from ExcelExportTool.generation import cs_generation
from ExcelExportTool.exceptions import WriteFileError


def test_generate_info_class_auto_adds_id():
    content = cs_generation.generate_info_class(
        "Item",
        {"name": "string"},
        {"name": "名称"},
    )
    assert 'JsonProperty("id")' in content
    assert 'public int id' in content


def test_write_to_file_dry_run_does_not_create_file(tmp_path):
    target = tmp_path / "A.cs"
    cs_generation.set_output_options(diff_only=True, dry_run=True)
    cs_generation.write_to_file("class A {}", str(target))
    assert not target.exists()
    cs_generation.set_output_options(diff_only=True, dry_run=False)


def test_write_to_file_raises_write_file_error_on_tempfile_failure(monkeypatch, tmp_path):
    target = tmp_path / "B.cs"

    def fake_mkstemp(*args, **kwargs):
        raise OSError("mkstemp failed")

    monkeypatch.setattr(cs_generation.tempfile, "mkstemp", fake_mkstemp)

    with pytest.raises(WriteFileError, match="写入文件失败"):
        cs_generation.write_to_file("class B {}", str(target))


def test_write_to_file_diff_only_keeps_existing_content(tmp_path):
    target = tmp_path / "C.cs"
    cs_generation.set_output_options(diff_only=True, dry_run=False)

    cs_generation.write_to_file("class C {}", str(target))
    mtime_1 = os.path.getmtime(target)
    cs_generation.write_to_file("class C {}", str(target))
    mtime_2 = os.path.getmtime(target)

    assert target.read_text(encoding="utf-8") == "class C {}"
    assert mtime_2 >= mtime_1
