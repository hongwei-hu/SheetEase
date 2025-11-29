import pytest
from ExcelExportTool import data_processing

def test_int_range():
    # 超范围应有警告
    # 实际测试
    # 超范围应有警告
    from contextlib import nullcontext
    with nullcontext():
        from unittest.mock import patch
        with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
            data_processing._check_csharp_primitive_range("int", 2**31, raw=str(2**31), field="test", sheet="sheet")
            mock_warn.assert_called()
    # 正常值无警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("int", 123, raw="123", field="test", sheet="sheet")
        mock_warn.assert_not_called()

def test_float_range():
    from unittest.mock import patch
    # 超范围应有警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("float", 3.5e38, raw="3.5e38", field="test", sheet="sheet")
        mock_warn.assert_called()
    # 正常值无警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("float", 1.0, raw="1.0", field="test", sheet="sheet")
        mock_warn.assert_not_called()

def test_bool_legal():
    from unittest.mock import patch
    # 非法应有警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("bool", True, raw="maybe", field="test", sheet="sheet")
        mock_warn.assert_called()
    # 合法值无警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("bool", True, raw="true", field="test", sheet="sheet")
        data_processing._check_csharp_primitive_range("bool", False, raw="0", field="test", sheet="sheet")
        data_processing._check_csharp_primitive_range("bool", True, raw="1", field="test", sheet="sheet")
        data_processing._check_csharp_primitive_range("bool", False, raw="false", field="test", sheet="sheet")
        mock_warn.assert_not_called()
    # 空值(None/"")不警告，解析为False
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("bool", False, raw=None, field="test", sheet="sheet")
        data_processing._check_csharp_primitive_range("bool", False, raw="", field="test", sheet="sheet")
        mock_warn.assert_not_called()

def test_string_length():
    from unittest.mock import patch
    # 超长应有警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("string", "a"*70000, raw="a...", field="test", sheet="sheet")
        mock_warn.assert_called()
    # 正常值无警告
    with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
        data_processing._check_csharp_primitive_range("string", "short", raw="short", field="test", sheet="sheet")
        mock_warn.assert_not_called()
