"""单元测试：type_utils模块"""
import pytest
from ExcelExportTool.utils.type_utils import validate_type_annotation, parse_type_annotation, convert_type_to_csharp
from ExcelExportTool.exceptions import ExportError


class TestValidateTypeAnnotation:
    """测试类型注解验证"""
    
    def test_valid_scalar_types(self):
        """测试有效的标量类型"""
        assert validate_type_annotation("int") == (True, "")
        assert validate_type_annotation("string") == (True, "")
        assert validate_type_annotation("float") == (True, "")
        assert validate_type_annotation("bool") == (True, "")
        assert validate_type_annotation("nnint") == (True, "")
        assert validate_type_annotation("nnfloat") == (True, "")
        assert validate_type_annotation("pint") == (True, "")
        assert validate_type_annotation("pfloat") == (True, "")
    
    def test_valid_list_types(self):
        """测试有效的列表类型"""
        assert validate_type_annotation("list(int)") == (True, "")
        assert validate_type_annotation("list(string)") == (True, "")
        assert validate_type_annotation("list(list(int))") == (True, "")
        assert validate_type_annotation("unilist(int)") == (True, "")
        assert validate_type_annotation("unilist(string)") == (True, "")
        assert validate_type_annotation("unilist(enum(TestEnum))") == (True, "")
    
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

        kind, base = parse_type_annotation("nnint")
        assert kind == "scalar"
        assert base == "int"

        kind, base = parse_type_annotation("nnfloat")
        assert kind == "scalar"
        assert base == "float"

        kind, base = parse_type_annotation("pint")
        assert kind == "scalar"
        assert base == "int"

        kind, base = parse_type_annotation("pfloat")
        assert kind == "scalar"
        assert base == "float"
    
    def test_parse_list(self):
        """测试解析列表类型"""
        kind, base = parse_type_annotation("list(int)")
        assert kind == "list"
        assert base == "int"
        
        kind, base = parse_type_annotation("list(string)")
        assert kind == "list"
        assert base == "string"
    
    def test_parse_unilist(self):
        """测试解析唯一性列表类型"""
        kind, base = parse_type_annotation("unilist(int)")
        assert kind == "unilist"
        assert base == "int"
        
        kind, base = parse_type_annotation("unilist(string)")
        assert kind == "unilist"
        assert base == "string"
        
        kind, base = parse_type_annotation("unilist(enum(TestEnum))")
        assert kind == "unilist"
        assert base == "enum(TestEnum)"
    
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
        assert convert_type_to_csharp("nnint") == "int"
        assert convert_type_to_csharp("nnfloat") == "float"
        assert convert_type_to_csharp("pint") == "int"
        assert convert_type_to_csharp("pfloat") == "float"
    
    def test_convert_list(self):
        """测试转换列表类型"""
        assert convert_type_to_csharp("list(int)") == "List<int>"
        assert convert_type_to_csharp("list(string)") == "List<string>"
    
    def test_convert_unilist(self):
        """测试转换唯一性列表类型"""
        assert convert_type_to_csharp("unilist(int)") == "List<int>"
        assert convert_type_to_csharp("unilist(string)") == "List<string>"
        assert convert_type_to_csharp("unilist(enum(TestEnum))") == "List<TestEnum>"
    
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

    def test_convert_types_with_constraints(self):
        """测试带约束的类型不会泄漏到 C# 类型声明中"""
        assert convert_type_to_csharp("int{min:1,max:5}") == "int"
        assert convert_type_to_csharp("string{nonempty,maxlen:32}") == "string"
        assert convert_type_to_csharp("list(int){nonempty,unique}") == "List<int>"
        assert convert_type_to_csharp("unilist(int){nonempty}") == "List<int>"
        assert convert_type_to_csharp("dict(string,int){minsize:1}") == "Dictionary<string,int>"
        assert convert_type_to_csharp("enum(Rarity){nonempty}") == "Rarity"

