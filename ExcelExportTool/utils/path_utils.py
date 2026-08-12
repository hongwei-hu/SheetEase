"""Path validation utilities for preventing path traversal attacks.

This module provides functions to validate and sanitize file paths,
ensuring they don't escape from allowed directories.
"""
import os
from pathlib import Path
from typing import Optional
from ..exceptions import PathTraversalError, InvalidPathError


# 这些目录由 SheetEase 及配套表格代理生成，只包含报告、备份或工作副本，
# 绝不能作为正式 Excel 数据源参与递归导出。
EXCLUDED_EXCEL_DIRECTORY_NAMES = frozenset({
    ".agent-excel",
    ".sheetease",
})


def is_excel_source_file(path: Path) -> bool:
    """判断路径是否为可参与导出的正式 Excel 文件。"""
    return (
        path.suffix.lower() == ".xlsx"
        and bool(path.name)
        and path.name[0].isupper()
        and not path.name.startswith("~$")
    )


def discover_excel_files(root: Path) -> list[Path]:
    """递归发现 Excel 文件，并明确排除工具生成的临时/元数据目录。"""
    root = Path(root)
    if not root.is_dir():
        return []

    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        # 就地裁剪，确保 os.walk 不会继续进入被排除目录。
        dir_names[:] = [
            name for name in dir_names
            if name.lower() not in EXCLUDED_EXCEL_DIRECTORY_NAMES
        ]
        current_path = Path(current_root)
        files.extend(
            current_path / name
            for name in file_names
            if name.lower().endswith(".xlsx")
        )
    return sorted(files, key=lambda path: str(path).casefold())


def validate_path(path: str, base_dir: Optional[str] = None) -> Path:
    """
    验证并规范化路径，防止路径遍历攻击
    
    Args:
        path: 要验证的路径字符串
        base_dir: 可选的基础目录，如果提供，确保路径在基础目录内
    
    Returns:
        规范化后的 Path 对象
    
    Raises:
        InvalidPathError: 路径无效
        PathTraversalError: 检测到路径遍历攻击
    """
    try:
        p = Path(path).resolve()
        
        # 如果指定了基础目录，确保路径在基础目录内
        if base_dir:
            base = Path(base_dir).resolve()
            try:
                # 检查路径是否在基础目录内
                p.relative_to(base)
            except ValueError:
                raise PathTraversalError(
                    str(p),
                    str(base),
                    context={'path': str(path), 'base_dir': str(base_dir)}
                )
        
        return p
    except PathTraversalError:
        raise
    except Exception as e:
        raise InvalidPathError(
            path,
            str(e),
            context={'path': path, 'base_dir': base_dir}
        )


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除危险字符
    
    Args:
        filename: 原始文件名
    
    Returns:
        清理后的文件名
    
    Raises:
        InvalidPathError: 文件名无效
    """
    if not filename or not isinstance(filename, str):
        raise InvalidPathError(filename, "文件名为空或不是字符串")
    
    # 移除路径分隔符和危险字符
    dangerous_chars = ['/', '\\', '..', '<', '>', ':', '"', '|', '?', '*']
    sanitized = filename
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '_')
    
    # 移除前导和尾随空格、点
    sanitized = sanitized.strip(' .')
    
    if not sanitized:
        raise InvalidPathError(filename, "清理后的文件名为空")
    
    return sanitized


def ensure_safe_path(path: str, base_dir: Optional[str] = None) -> Path:
    """
    确保路径安全：验证路径并防止路径遍历
    
    Args:
        path: 要验证的路径
        base_dir: 可选的基础目录
    
    Returns:
        安全的 Path 对象
    """
    # 先清理路径中的危险字符
    safe_path = path.replace('..', '').replace('//', '/').replace('\\\\', '\\')
    
    # 验证路径
    return validate_path(safe_path, base_dir)

