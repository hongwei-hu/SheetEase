"""
命名配置（默认保持当前行为）：
JSON: {name}Config.json
主脚本文件: {name}Data.cs
枚举键文件: {name}Keys.cs
"""
JSON_FILE_PATTERN = "{name}Config.json"
CS_FILE_SUFFIX = "Data"
ENUM_KEYS_SUFFIX = "Keys"

# ===== 新增可配置项 =====
# 是否对 JSON 中对象键进行字典序排序；设为 True 则稳定 diff，但会打乱原列顺序
JSON_SORT_KEYS = False
# 是否将每条记录的 id 字段放在最前（若 Excel 第一字段并非 id，也会自动补id并放前）
JSON_ID_FIRST = True

# ===== 引用检查相关配置 =====
# 当引用字段为 int 类型时，将这些取值视为“空引用”，跳过存在性检查
REFERENCE_ALLOW_EMPTY_INT_VALUES = {0}

# 当引用字段为 string 类型时，将这些取值视为“空引用”，跳过存在性检查
REFERENCE_ALLOW_EMPTY_STRING_VALUES = {""}

# JSON size warning thresholds (bytes)
# - 如果序列化后的 JSON 总体积超过 JSON_WARN_TOTAL_BYTES，将打印警告，防止意外生成超大文件耗尽内存或磁盘
# - 如果单条记录的序列化字节数超过 JSON_WARN_RECORD_BYTES，将打印警告并停止进一步逐条大小检查以节省时间
# 默认值：总体 4MB，单条 512KB。可在调用前修改这些常量以适配项目需求。
JSON_WARN_TOTAL_BYTES = 4 * 1024 * 1024
JSON_WARN_RECORD_BYTES = 1 * 512 * 1024