"""Type definitions and constants for worksheet data processing."""
import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# 组合键参数（默认保证合并结果可装入 int32）
MAX_KEY2 = 46340         # key2 的上限（exclusive）：0 <= key2 < MAX_KEY2
MULTIPLIER = MAX_KEY2    # MULTIPLIER = MAX_KEY2

# 正则表达式模式
KEY1_PREFIX_RE = re.compile(r"^\s*key1\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
KEY2_PREFIX_RE = re.compile(r"^\s*key2\s*:\s*(?P<name>.+)\s*$", re.IGNORECASE)
# [Sheet/Field]FieldName 或 [Sheet]FieldName（省略 Field -> 默认 id）
# 引用标记：[Sheet/Field]FieldName（Sheet 名不允许包含 ':'，避免与 [Asset:ext] 混淆）
REF_PREFIX_RE = re.compile(r"^\s*\[(?P<sheet>[^:/\]]+)(?:/(?P<field>[^\]]+))?\]\s*(?P<name>.+)$")
# [Asset]FieldName 或 [Asset:png]FieldName —— 资源文件校验标记
ASSET_PREFIX_RE = re.compile(r"^\s*\[(?:asset)(?::(?P<ext>[A-Za-z0-9_]+))?\]\s*(?P<name>.+)$", re.IGNORECASE)

# 可选字段统计开关
PRINT_FIELD_SUMMARY = True

