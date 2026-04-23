# Author: huhongwei 306463233@qq.com
# MIT License
"""
字段约束检查模块。

支持在类型注解末尾附加约束配置块，格式为 `类型{约束1, 约束2:值, ...}`。

支持的约束类型示例：
  int{min:0, max:100}
  float{min:0.0, max:1.0}
  string{nonempty, maxlen:64}
  string{pattern:"^[A-Z_]+$"}
  list(int){nonempty, unique}
  list(string){minlen:1, maxlen:5}
  dict(string,int){minsize:1, maxsize:10}
"""
import re
from typing import Any, Dict, List, Tuple

# 匹配末尾的 {...} 约束块（不允许嵌套花括号）
_CONSTRAINT_BLOCK_RE = re.compile(r'^(.*?)(\{[^{}]*\})\s*$', re.DOTALL)


def split_type_and_constraint_str(type_str: str) -> Tuple[str, str]:
    """
    分离类型字符串和约束字符串。

    Returns:
        (pure_type, constraint_str)
        无约束时 constraint_str 为空字符串。

    Examples:
        "int{min:0, max:100}"  ->  ("int", "min:0, max:100")
        "list(int){nonempty}"  ->  ("list(int)", "nonempty")
        "string"               ->  ("string", "")
    """
    if not type_str or '{' not in type_str:
        return (type_str or "").strip(), ""
    m = _CONSTRAINT_BLOCK_RE.match(type_str.strip())
    if m:
        return m.group(1).strip(), m.group(2)[1:-1].strip()  # strip outer {}
    return type_str.strip(), ""


def parse_constraint_str(constraint_str: str) -> Dict[str, Any]:
    """
    将约束字符串解析为约束字典。

    支持以下格式：
      - 布尔标志: ``nonempty`` -> ``{"nonempty": True}``
      - 数字约束: ``min:0``    -> ``{"min": 0}``（整数或浮点数）
      - 字符串值: ``pattern:"^[A-Z]+$"`` -> ``{"pattern": "^[A-Z]+$"}``

    Returns:
        约束字典，key 为约束名（小写），value 为约束值。
    """
    result: Dict[str, Any] = {}
    if not constraint_str:
        return result

    parts = _split_by_comma_respecting_quotes(constraint_str)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            key, _, val = part.partition(':')
            key = key.strip().lower()
            val = val.strip()
            # 去掉外层引号
            if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                result[key] = val[1:-1]
            else:
                # 尝试解析为数字
                try:
                    if '.' in val:
                        result[key] = float(val)
                    else:
                        result[key] = int(val)
                except ValueError:
                    result[key] = val
        else:
            # 布尔标志型约束
            result[part.lower()] = True

    return result


def _split_by_comma_respecting_quotes(s: str) -> List[str]:
    """按逗号分割字符串，引号内的逗号不作分割符。"""
    parts: List[str] = []
    current: List[str] = []
    in_quote: str | None = None
    for ch in s:
        if ch in ('"', "'"):
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
            current.append(ch)
        elif ch == ',' and in_quote is None:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current))
    return parts


def check_constraints(
    value: Any,
    constraints: Dict[str, Any],
    type_kind: str,
    type_base: str,
    field_name: str,
    sheet_name: str,
    excel_row: int,
) -> List[str]:
    """
    检查值是否满足所有约束。

    Args:
        value:       已转换后的字段值
        constraints: 约束字典（由 parse_constraint_str 生成）
        type_kind:   类型种类（"scalar" / "list" / "dict" / "enum"）
        type_base:   基础类型（"int" / "float" / "string" / "bool" / ...）
        field_name:  字段名（用于错误消息）
        sheet_name:  工作表名（用于错误消息）
        excel_row:   Excel 行号（用于错误消息）

    Returns:
        违规消息列表，空列表表示通过所有约束。
    """
    if value is None or not constraints:
        return []

    violations: List[str] = []
    loc = f"[{sheet_name}] 字段 '{field_name}' 第{excel_row}行"

    if type_kind == "scalar":
        if type_base in ("int", "float"):
            violations.extend(_check_numeric(value, constraints, loc))
        elif type_base == "string":
            violations.extend(_check_string(value, constraints, loc))
        # bool / enum 暂无约束
    elif type_kind == "list":
        violations.extend(_check_list(value, constraints, loc))
    elif type_kind == "dict":
        violations.extend(_check_dict(value, constraints, loc))

    return violations


# ─────────────────────── 各类型约束检查 ───────────────────────

def _check_numeric(value: Any, constraints: Dict[str, Any], loc: str) -> List[str]:
    violations: List[str] = []
    try:
        v = float(value)
    except (TypeError, ValueError):
        return violations

    if "min" in constraints:
        mn = float(constraints["min"])
        if v < mn:
            violations.append(f"{loc}: 值 {value} 小于最小值 {constraints['min']}")
    if "max" in constraints:
        mx = float(constraints["max"])
        if v > mx:
            violations.append(f"{loc}: 值 {value} 大于最大值 {constraints['max']}")
    if "min_exclusive" in constraints:
        mn = float(constraints["min_exclusive"])
        if v <= mn:
            violations.append(f"{loc}: 值 {value} 应严格大于 {constraints['min_exclusive']}（不含边界）")
    if "max_exclusive" in constraints:
        mx = float(constraints["max_exclusive"])
        if v >= mx:
            violations.append(f"{loc}: 值 {value} 应严格小于 {constraints['max_exclusive']}（不含边界）")
    if constraints.get("nonzero"):
        if v == 0:
            violations.append(f"{loc}: 值不能为 0（nonzero 约束）")
    if constraints.get("positive"):
        if v <= 0:
            violations.append(f"{loc}: 值 {value} 应为正数（> 0）")
    if constraints.get("nonnegative"):
        if v < 0:
            violations.append(f"{loc}: 值 {value} 应为非负数（>= 0）")
    return violations


def _check_string(value: Any, constraints: Dict[str, Any], loc: str) -> List[str]:
    violations: List[str] = []
    s = str(value) if value is not None else ""

    if constraints.get("nonempty"):
        if not s.strip():
            violations.append(f"{loc}: 字符串不能为空（nonempty 约束）")
    if "minlen" in constraints:
        mn = int(constraints["minlen"])
        if len(s) < mn:
            violations.append(f"{loc}: 字符串长度 {len(s)} 小于最小长度 {mn}")
    if "maxlen" in constraints:
        mx = int(constraints["maxlen"])
        if len(s) > mx:
            violations.append(f"{loc}: 字符串长度 {len(s)} 超过最大长度 {mx}")
    if "len" in constraints:
        expected = int(constraints["len"])
        if len(s) != expected:
            violations.append(f"{loc}: 字符串长度 {len(s)} 不等于要求的固定长度 {expected}")
    if "pattern" in constraints:
        pat = str(constraints["pattern"])
        try:
            if not re.fullmatch(pat, s):
                violations.append(f"{loc}: 字符串 '{s}' 不匹配格式 {pat}")
        except re.error as e:
            violations.append(f"{loc}: pattern 正则表达式无效: {pat} -> {e}")
    return violations


def _check_list(value: Any, constraints: Dict[str, Any], loc: str) -> List[str]:
    violations: List[str] = []
    if not isinstance(value, list):
        return violations

    if constraints.get("nonempty"):
        if len(value) == 0:
            violations.append(f"{loc}: 列表不能为空（nonempty 约束）")
    if "minlen" in constraints:
        mn = int(constraints["minlen"])
        if len(value) < mn:
            violations.append(f"{loc}: 列表长度 {len(value)} 小于最小长度 {mn}")
    if "maxlen" in constraints:
        mx = int(constraints["maxlen"])
        if len(value) > mx:
            violations.append(f"{loc}: 列表长度 {len(value)} 超过最大长度 {mx}")
    if constraints.get("unique"):
        seen: list = []
        dups: list = []
        for item in value:
            if item in seen:
                if item not in dups:
                    dups.append(item)
            else:
                seen.append(item)
        if dups:
            violations.append(f"{loc}: 列表存在重复元素: {dups[:5]}")
    return violations


def _check_dict(value: Any, constraints: Dict[str, Any], loc: str) -> List[str]:
    violations: List[str] = []
    if not isinstance(value, dict):
        return violations

    if constraints.get("nonempty"):
        if len(value) == 0:
            violations.append(f"{loc}: 字典不能为空（nonempty 约束）")
    if "minsize" in constraints:
        mn = int(constraints["minsize"])
        if len(value) < mn:
            violations.append(f"{loc}: 字典条目数 {len(value)} 小于最小值 {mn}")
    if "maxsize" in constraints:
        mx = int(constraints["maxsize"])
        if len(value) > mx:
            violations.append(f"{loc}: 字典条目数 {len(value)} 超过最大值 {mx}")
    return violations
