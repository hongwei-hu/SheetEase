"""单元测试：data_processing模块"""
import pytest
from ExcelExportTool.data_processing import convert_to_type, PRIMITIVE_TYPE_MAPPING
from ExcelExportTool.exceptions import ExportError


class TestConvertPrimitiveTypes:
    """测试基础类型转换"""
    
    def test_convert_int(self):
        """测试int类型转换"""
        assert convert_to_type("int", "123") == 123
        assert convert_to_type("int", "-456") == -456
        assert convert_to_type("int", 789) == 789
    
    def test_convert_int_overflow(self):
        """测试int溢出"""
        # 超出C# int范围的值应该发出警告，但不抛出异常
        from unittest.mock import patch
        with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
            # 应该成功转换，但会发出警告
            result = convert_to_type("int", "2147483648")
            assert result == 2147483648
            mock_warn.assert_called_once()
        
        with patch('ExcelExportTool.data_processing.log_warn') as mock_warn:
            result = convert_to_type("int", "-2147483649")
            assert result == -2147483649
            mock_warn.assert_called_once()
    
    def test_convert_float(self):
        """测试float类型转换"""
        assert convert_to_type("float", "123.45") == 123.45
        assert convert_to_type("float", "-67.89") == -67.89
    
    def test_convert_bool(self):
        """测试bool类型转换"""
        assert convert_to_type("bool", "true") is True
        assert convert_to_type("bool", "1") is True
        assert convert_to_type("bool", "false") is False
        assert convert_to_type("bool", "0") is False
        assert convert_to_type("bool", None) is False
        assert convert_to_type("bool", "") is False
    
    def test_convert_string(self):
        """测试string类型转换"""
        assert convert_to_type("string", "hello") == "hello"
        assert convert_to_type("string", 123) == "123"
        assert convert_to_type("string", None) == ""


class TestConvertListTypes:
    """测试列表类型转换"""
    
    def test_convert_list_int(self):
        """测试int列表转换"""
        result = convert_to_type("list(int)", "1,2,3")
        assert result == [1, 2, 3]
    
    def test_convert_list_string(self):
        """测试string列表转换"""
        result = convert_to_type("list(string)", "a,b,c")
        assert result == ["a", "b", "c"]
    
    def test_convert_empty_list(self):
        """测试空列表"""
        result = convert_to_type("list(int)", None)
        assert result == []
        
        result = convert_to_type("list(int)", "")
        assert result == []


class TestConvertDictTypes:
    """测试字典类型转换"""
    
    def test_convert_dict(self):
        """测试字典转换"""
        result = convert_to_type("dict(int,string)", "1:a\n2:b")
        assert result == {1: "a", 2: "b"}
    
    def test_convert_empty_dict(self):
        """测试空字典"""
        result = convert_to_type("dict(int,string)", None)
        assert result == {}


class TestTypeValidation:
    """测试类型验证"""
    
    def test_empty_type_string(self):
        """测试空类型字符串"""
        with pytest.raises(ValueError, match="空类型定义"):
            convert_to_type("", "value")
        
        with pytest.raises(ValueError, match="空类型定义"):
            convert_to_type("   ", "value")

