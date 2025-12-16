"""单元测试：type_utils模块"""
import pytest
from ExcelExportTool.type_utils import validate_type_annotation, parse_type_annotation, convert_type_to_csharp
from ExcelExportTool.exceptions import ExportError


class TestValidateTypeAnnotation:
    """测试类型注解验证"""
    
    def test_valid_scalar_types(self):
        """测试有效的标量类型"""
        assert validate_type_annotation("int") == (True, "")
        assert validate_type_annotation("string") == (True, "")
        assert validate_type_annotation("float") == (True, "")
        assert validate_type_annotation("bool") == (True, "")
    
    def test_valid_list_types(self):
        """测试有效的列表类型"""
        assert validate_type_annotation("list(int)") == (True, "")
        assert validate_type_annotation("list(string)") == (True, "")
        assert validate_type_annotation("list(list(int))") == (True, "")
    
    def test_valid_dict_types(self):
        """测试有效的字典类型"""
        assert validate_type_annotation("dict(int,string)") == (True, "")
        assert validate_type_annotation("dict(string,int)") == (True, "")
    
    def test_valid_enum_types(self):
        """测试有效的枚举类型"""
        assert validate_type_annotation("enum(TestEnum)") == (True, "")
        assert validate_type_annotation("list(enum(TestEnum))") == (True, "")
    
    def test_invalid_bracket_mismatch(self):
        """测试括号不匹配"""
        valid, msg = validate_type_annotation("list(int")
        assert not valid
        assert "括号不匹配" in msg
        
        valid, msg = validate_type_annotation("list(int))")
        assert not valid
        assert "括号不匹配" in msg
    
    def test_invalid_nested_too_deep(self):
        """测试嵌套过深"""
        valid, msg = validate_type_annotation("list(list(list(list(int))))")
        assert not valid
        assert "嵌套深度过深" in msg
    
    def test_invalid_empty(self):
        """测试空类型"""
        valid, msg = validate_type_annotation("")
        assert not valid
        assert "为空" in msg
        
        valid, msg = validate_type_annotation("   ")
        assert not valid
        assert "为空" in msg
    
    def test_invalid_bracket_order(self):
        """测试括号顺序错误"""
        valid, msg = validate_type_annotation("list)int(")
        assert not valid
        assert "括号顺序错误" in msg


class TestParseTypeAnnotation:
    """测试类型注解解析"""
    
    def test_parse_scalar(self):
        """测试解析标量类型"""
        kind, base = parse_type_annotation("int")
        assert kind == "scalar"
        assert base == "int"
        
        kind, base = parse_type_annotation("string")
        assert kind == "scalar"
        assert base == "string"
    
    def test_parse_list(self):
        """测试解析列表类型"""
        kind, base = parse_type_annotation("list(int)")
        assert kind == "list"
        assert base == "int"
        
        kind, base = parse_type_annotation("list(string)")
        assert kind == "list"
        assert base == "string"
    
    def test_parse_enum(self):
        """测试解析枚举类型"""
        kind, base = parse_type_annotation("enum(TestEnum)")
        assert kind == "enum"
        assert base == "TestEnum"
    
    def test_parse_list_enum(self):
        """测试解析枚举列表类型"""
        kind, base = parse_type_annotation("list(enum(TestEnum))")
        assert kind == "list"
        assert base == "enum(TestEnum)"


class TestConvertTypeToCsharp:
    """测试类型转换为C#"""
    
    def test_convert_scalar(self):
        """测试转换标量类型"""
        assert convert_type_to_csharp("int") == "int"
        assert convert_type_to_csharp("string") == "string"
        assert convert_type_to_csharp("float") == "float"
    
    def test_convert_list(self):
        """测试转换列表类型"""
        assert convert_type_to_csharp("list(int)") == "List<int>"
        assert convert_type_to_csharp("list(string)") == "List<string>"
    
    def test_convert_enum(self):
        """测试转换枚举类型"""
        assert convert_type_to_csharp("enum(TestEnum)") == "TestEnum"
    
    def test_convert_list_enum(self):
        """测试转换枚举列表类型"""
        assert convert_type_to_csharp("list(enum(TestEnum))") == "List<TestEnum>"
    
    def test_convert_dict(self):
        """测试转换字典类型"""
        assert convert_type_to_csharp("dict(int,string)") == "Dictionary<int,string>"
        assert convert_type_to_csharp("dict(string,int)") == "Dictionary<string,int>"

