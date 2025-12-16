"""Naming helper utilities (C# identifier checks).

Extracted from data_processing.py to centralize naming rules.
"""
import re

# C# keywords (common set)
_C_SHARP_KEYWORDS = set([
    'abstract','as','base','bool','break','byte','case','catch','char','checked','class','const','continue',
    'decimal','default','delegate','do','double','else','enum','event','explicit','extern','false','finally',
    'fixed','float','for','foreach','goto','if','implicit','in','int','interface','internal','is','lock','long',
    'namespace','new','null','object','operator','out','override','params','private','protected','public','readonly',
    'ref','return','sbyte','sealed','short','sizeof','stackalloc','static','string','struct','switch','this','throw',
    'true','try','typeof','uint','ulong','unchecked','unsafe','ushort','using','virtual','void','volatile','while'
])


def is_valid_csharp_identifier(name: str) -> bool:
    """Return True if name is a valid C# identifier (basic check).

    Rules:
    - non-empty string
    - starts with A-Za-z or underscore
    - contains only A-Za-z0-9_ thereafter
    - not a C# keyword
    """
    if not isinstance(name, str) or not name:
        return False
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        return False
    if name in _C_SHARP_KEYWORDS:
        return False
    return True
