# Author: huhongwei 306463233@qq.com
# MIT License
"""枚举注册表：管理所有枚举定义，提供枚举验证和值转换功能"""
from typing import Dict, Set, Optional, Tuple
from .naming_utils import is_valid_csharp_identifier
from .log import log_error
from .exceptions import ExportError


class EnumRegistry:
    """枚举注册表：管理所有枚举定义"""
    
    def __init__(self):
        # 枚举名 -> {枚举项名称 -> 枚举值}
        self._enums: Dict[str, Dict[str, int]] = {}
        # 枚举名 -> 命名空间
        self._enum_namespaces: Dict[str, str] = {}
        # 枚举名 -> 来源信息（用于错误提示）
        self._enum_sources: Dict[str, str] = {}
    
    def register_enum(self, enum_name: str, enum_items: Dict[str, int], namespace: str = "Data.TableScript", source: str = "") -> None:
        """
        注册一个枚举
        
        Args:
            enum_name: 枚举类型名称（如 "SampleDataKeys"）
            enum_items: 枚举项名称到枚举值的映射（如 {"ItemA": 0, "ItemB": 1}）
            namespace: 枚举所在的命名空间
            source: 枚举来源信息（用于错误提示，如 "文件A.xlsx" 或 "文件B.xlsx/Enum-ItemType"）
        
        Raises:
            ExportError: 如果枚举重复定义（即使枚举项相同也不允许）
        """
        if not is_valid_csharp_identifier(enum_name):
            raise ExportError(f"枚举类型名称不符合C#命名规范: {enum_name}")
        
        if enum_name in self._enums:
            # 检查是否重复定义
            existing_items = set(self._enums[enum_name].keys())
            new_items = set(enum_items.keys())
            existing_source = self._enum_sources.get(enum_name, "未知来源")
            
            if existing_items != new_items:
                # 枚举项不一致
                raise ExportError(
                    f"枚举 {enum_name} 重复定义，但枚举项不一致。\n"
                    f"已有定义（来源: {existing_source}）: {sorted(existing_items)}\n"
                    f"新定义（来源: {source}）: {sorted(new_items)}"
                )
            else:
                # 枚举项相同，但仍然不允许重复定义
                raise ExportError(
                    f"枚举 {enum_name} 重复定义。\n"
                    f"已有定义（来源: {existing_source}）\n"
                    f"重复定义（来源: {source}）\n"
                    f"即使枚举项相同，也不允许在不同位置重复定义同一个枚举。"
                )
        
        self._enums[enum_name] = enum_items.copy()
        self._enum_namespaces[enum_name] = namespace
        self._enum_sources[enum_name] = source
    
    def has_enum(self, enum_name: str) -> bool:
        """检查枚举是否存在"""
        return enum_name in self._enums
    
    def get_enum_items(self, enum_name: str) -> Dict[str, int]:
        """获取枚举的所有项（枚举项名称 -> 枚举值）"""
        if enum_name not in self._enums:
            raise ExportError(f"枚举 {enum_name} 未定义")
        return self._enums[enum_name].copy()
    
    def get_enum_value(self, enum_name: str, item_name: str) -> int:
        """
        获取枚举项对应的枚举值
        
        Args:
            enum_name: 枚举类型名称
            item_name: 枚举项名称（区分大小写）
        
        Returns:
            枚举值（整数）
        
        Raises:
            ExportError: 如果枚举或枚举项不存在
        """
        if enum_name not in self._enums:
            raise ExportError(f"枚举 {enum_name} 未定义")
        
        enum_items = self._enums[enum_name]
        if item_name not in enum_items:
            available_items = sorted(enum_items.keys())
            raise ExportError(
                f"枚举 {enum_name} 中不存在枚举项 '{item_name}'。"
                f"可用的枚举项: {available_items}"
            )
        
        return enum_items[item_name]
    
    def validate_enum_item(self, enum_name: str, item_name: str) -> bool:
        """
        验证枚举项是否存在
        
        Args:
            enum_name: 枚举类型名称
            item_name: 枚举项名称
        
        Returns:
            True 如果存在，False 如果不存在
        """
        if enum_name not in self._enums:
            return False
        return item_name in self._enums[enum_name]
    
    def validate_enum_item_name(self, item_name: str) -> bool:
        """
        验证枚举项名称是否符合C#命名规范（大写驼峰式）
        
        Args:
            item_name: 枚举项名称
        
        Returns:
            True 如果符合规范
        """
        if not item_name:
            return False
        # 必须符合C#标识符规范
        if not is_valid_csharp_identifier(item_name):
            return False
        # 必须以大写字母开头（大写驼峰式）
        if not item_name[0].isupper():
            return False
        return True
    
    def get_all_enum_names(self) -> Set[str]:
        """获取所有已注册的枚举名称"""
        return set(self._enums.keys())
    
    def get_namespace(self, enum_name: str) -> str:
        """获取枚举的命名空间"""
        return self._enum_namespaces.get(enum_name, "Data.TableScript")


# 全局枚举注册表实例
_global_enum_registry: Optional[EnumRegistry] = None


def get_enum_registry() -> EnumRegistry:
    """获取全局枚举注册表实例"""
    global _global_enum_registry
    if _global_enum_registry is None:
        _global_enum_registry = EnumRegistry()
    return _global_enum_registry


def reset_enum_registry() -> None:
    """重置枚举注册表（用于测试或重新开始）"""
    global _global_enum_registry
    _global_enum_registry = None

