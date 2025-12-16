"""单元测试：path_utils模块"""
import pytest
import tempfile
import os
from pathlib import Path
from ExcelExportTool.utils.path_utils import validate_path, sanitize_filename, ensure_safe_path
from ExcelExportTool.exceptions import PathTraversalError, InvalidPathError


class TestValidatePath:
    """测试路径验证"""
    
    def test_valid_path(self):
        """测试有效路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = validate_path(tmpdir)
            assert isinstance(p, Path)
            assert p.exists()
    
    def test_path_with_base_dir(self):
        """测试带基础目录的路径验证"""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir, exist_ok=True)
            
            # 在基础目录内的路径应该成功
            p = validate_path(subdir, tmpdir)
            assert isinstance(p, Path)
            
            # 在基础目录外的路径应该失败
            with pytest.raises(PathTraversalError):
                validate_path("/tmp", tmpdir)
    
    def test_path_traversal_detection(self):
        """测试路径遍历检测"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(PathTraversalError):
                validate_path("../../etc/passwd", tmpdir)
            
            with pytest.raises(PathTraversalError):
                validate_path("../..", tmpdir)


class TestSanitizeFilename:
    """测试文件名清理"""
    
    def test_valid_filename(self):
        """测试有效文件名"""
        assert sanitize_filename("test.txt") == "test.txt"
        assert sanitize_filename("my_file.xlsx") == "my_file.xlsx"
    
    def test_remove_dangerous_chars(self):
        """测试移除危险字符"""
        # "../" 被替换为 "___" (3个字符 -> 3个下划线)
        assert sanitize_filename("test/../file.txt") == "test___file.txt"
        assert sanitize_filename("file<name>.txt") == "file_name_.txt"
        assert sanitize_filename("file:name|txt") == "file_name_txt"
    
    def test_remove_leading_trailing_dots(self):
        """测试移除前导和尾随点"""
        assert sanitize_filename(".hidden") == "hidden"
        assert sanitize_filename("file.") == "file"
        # ".." 被替换为 "_"，strip(' .') 只去掉点和空格，不去掉下划线
        assert sanitize_filename("..file..") == "_file_"
    
    def test_empty_filename(self):
        """测试空文件名"""
        with pytest.raises(InvalidPathError):
            sanitize_filename("")
        
        with pytest.raises(InvalidPathError):
            sanitize_filename("   ")


class TestEnsureSafePath:
    """测试确保路径安全"""
    
    def test_safe_path(self):
        """测试安全路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ensure_safe_path(tmpdir)
            assert isinstance(p, Path)
    
    def test_path_with_dangerous_chars(self):
        """测试包含危险字符的路径"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 路径中的 .. 应该被移除
            safe_path = ensure_safe_path(os.path.join(tmpdir, "..", "test"))
            # 验证路径在基础目录内
            assert tmpdir in str(safe_path) or safe_path.exists()

