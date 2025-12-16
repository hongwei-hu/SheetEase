from typing import Any, Dict, Optional


class ExportError(Exception):
    """基础导表异常，支持上下文信息"""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        """
        初始化导出异常
        
        Args:
            message: 错误消息
            context: 可选的上下文信息字典，包含 file, sheet, row, col 等
        """
        super().__init__(message)
        self.context = dict(context) if context else {}
        self._format_message()
    
    def _format_message(self):
        """格式化错误信息，包含上下文"""
        parts = [str(self.args[0])]
        if self.context:
            ctx_parts = []
            if 'file' in self.context:
                ctx_parts.append(f"文件: {self.context['file']}")
            if 'sheet' in self.context:
                ctx_parts.append(f"表: {self.context['sheet']}")
            if 'row' in self.context:
                ctx_parts.append(f"行: {self.context['row']}")
            if 'col' in self.context:
                ctx_parts.append(f"列: {self.context['col']}")
            if ctx_parts:
                parts.append("(" + ", ".join(ctx_parts) + ")")
        self.args = (" ".join(parts),)

class DuplicateFieldError(ExportError):
    def __init__(self, fields):
        super().__init__(f"发现重复字段: {sorted(fields)}")

class InvalidEnumNameError(ExportError):
    def __init__(self, name, row):
        super().__init__(f"非法枚举名 '{name}' (Excel 行: {row})")

class DuplicatePrimaryKeyError(ExportError):
    def __init__(self, key, row_a, row_b):
        super().__init__(f"主键重复: {key} (行 {row_a} 与 行 {row_b})")

class CompositeKeyOverflowError(ExportError):
    def __init__(self, combined):
        super().__init__(f"组合键溢出: {combined} >= 2^31")

class SheetNameConflictError(ExportError):
    def __init__(self, sheet, f1, f2):
        super().__init__(f"工作表命名冲突: {sheet} 出现在 {f1} 与 {f2}")

class UnknownCustomTypeError(ExportError):
    def __init__(self, type_name: str, field: str | None = None, sheet: str | None = None):
        loc = []
        if field:
            loc.append(f"字段:{field}")
        if sheet:
            loc.append(f"表:{sheet}")
        suffix = (" (" + ", ".join(loc) + ")") if loc else ""
        super().__init__(f"未注册的自定义类型: {type_name}{suffix}")

class CustomTypeParseError(ExportError):
    def __init__(self, type_name: str, raw: str, reason: str, field: str | None = None, sheet: str | None = None):
        loc = []
        if field:
            loc.append(f"字段:{field}")
        if sheet:
            loc.append(f"表:{sheet}")
        suffix = (" (" + ", ".join(loc) + ")") if loc else ""
        super().__init__(f"自定义类型解析失败: {type_name} 原值:[{raw}] -> {reason}{suffix}")


class InvalidFieldNameError(ExportError):
    def __init__(self, field: str, col_index: int, sheet: str):
        super().__init__(f"非法字段名: '{field}' 在表 '{sheet}' 列索引 {col_index} 不符合 C# 命名规范")


class WriteFileError(ExportError):
    def __init__(self, path: str, reason: str):
        super().__init__(f"写入文件失败: {path} -> {reason}")


class HeaderFormatError(ExportError):
    def __init__(self, sheet: str, reason: str):
        super().__init__(f"表头格式错误: {sheet} -> {reason}")


# ==================== 新增异常类型 ====================

class ExcelFileCorruptedError(ExportError):
    """Excel文件损坏或无法打开"""
    def __init__(self, file_path: str, reason: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(f"Excel文件损坏: {file_path} -> {reason}", context)


class SheetStructureError(ExportError):
    """Sheet结构错误"""
    def __init__(self, sheet: str, reason: str, context: Optional[Dict[str, Any]] = None):
        ctx = dict(context) if context else {}
        ctx['sheet'] = sheet
        super().__init__(f"Sheet结构错误: {sheet} -> {reason}", ctx)


class DataTypeMismatchError(ExportError):
    """数据类型不匹配"""
    def __init__(self, expected: str, actual: str, value: Any, context: Optional[Dict[str, Any]] = None):
        ctx = dict(context) if context else {}
        super().__init__(
            f"数据类型不匹配: 期望 {expected}，实际 {actual}，值: {value}",
            ctx
        )


class MemoryLimitExceededError(ExportError):
    """内存限制超出"""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(f"内存限制超出: {message}", context)


class PathTraversalError(ExportError):
    """路径遍历攻击检测"""
    def __init__(self, path: str, base_dir: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        msg = f"路径遍历检测: {path}"
        if base_dir:
            msg += f" (基础目录: {base_dir})"
        super().__init__(msg, context)


class InvalidPathError(ExportError):
    """无效路径"""
    def __init__(self, path: str, reason: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(f"无效路径: {path} -> {reason}", context)