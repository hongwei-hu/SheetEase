"""单元测试：exceptions模块"""
import pytest
from ExcelExportTool.exceptions import (
    ExportError,
    ExcelFileCorruptedError,
    SheetStructureError,
    DataTypeMismatchError,
    MemoryLimitExceededError,
    PathTraversalError,
    InvalidPathError,
    DuplicatePrimaryKeyError,
    CompositeKeyOverflowError,
)


class TestExportError:
    """测试基础异常类"""
    
    def test_basic_error(self):
        """测试基础错误"""
        error = ExportError("测试错误")
        assert str(error) == "测试错误"
        assert error.context == {}
    
    def test_error_with_context(self):
        """测试带上下文的错误"""
        context = {"file": "test.xlsx", "sheet": "Sheet1", "row": 5}
        error = ExportError("测试错误", context)
        assert "测试错误" in str(error)
        assert "文件: test.xlsx" in str(error)
        assert "表: Sheet1" in str(error)
        assert "行: 5" in str(error)
        assert error.context == context


class TestExcelFileCorruptedError:
    """测试Excel文件损坏异常"""
    
    def test_file_corrupted_error(self):
        """测试文件损坏错误"""
        error = ExcelFileCorruptedError("test.xlsx", "无法打开文件")
        assert "Excel文件损坏" in str(error)
        assert "test.xlsx" in str(error)
        assert "无法打开文件" in str(error)


class TestSheetStructureError:
    """测试Sheet结构错误异常"""
    
    def test_sheet_structure_error(self):
        """测试Sheet结构错误"""
        error = SheetStructureError("Sheet1", "表头格式不正确")
        assert "Sheet结构错误" in str(error)
        assert "Sheet1" in str(error)
        assert error.context["sheet"] == "Sheet1"


class TestDataTypeMismatchError:
    """测试数据类型不匹配异常"""
    
    def test_data_type_mismatch_error(self):
        """测试数据类型不匹配错误"""
        error = DataTypeMismatchError("int", "string", "abc")
        assert "数据类型不匹配" in str(error)
        assert "期望 int" in str(error)
        assert "实际 string" in str(error)


class TestPathTraversalError:
    """测试路径遍历异常"""
    
    def test_path_traversal_error(self):
        """测试路径遍历错误"""
        error = PathTraversalError("../../etc/passwd", "/safe/dir")
        assert "路径遍历检测" in str(error)
        assert "../../etc/passwd" in str(error)
        assert "/safe/dir" in str(error)


class TestDuplicatePrimaryKeyError:
    """测试主键重复异常"""
    
    def test_duplicate_primary_key_error(self):
        """测试主键重复错误"""
        error = DuplicatePrimaryKeyError(123, 5, 10)
        assert "主键重复" in str(error)
        assert "123" in str(error)
        assert "行 5" in str(error)
        assert "行 10" in str(error)


class TestCompositeKeyOverflowError:
    """测试组合键溢出异常"""
    
    def test_composite_key_overflow_error(self):
        """测试组合键溢出错误"""
        error = CompositeKeyOverflowError(2147483648)
        assert "组合键溢出" in str(error)
        assert "2147483648" in str(error)

