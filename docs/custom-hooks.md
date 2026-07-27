# SheetEase 工程自定义检查钩子开发手册

工程自定义检查钩子用于承载只属于具体项目的业务规则，例如经济数值关系、配置组合合法性、本地化完整性或多表一致性。钩子只负责检查，不修改导出数据。

## 运行时机与失败策略

导出流程为：读取 Excel → 构建标准化内存数据 → 运行自定义检查 → 写入 JSON/C#/枚举 → 引用检查与清理。

- GUI 未配置“自定义检查钩子目录”时，完全跳过该阶段。
- `error` 会阻止本次导出文件的写入和旧文件清理。
- `warning` 与 `info` 会显示在日志中，但不会阻止导出。
- 清单加载失败、入口不存在、检查器抛异常或返回非法对象，均按 `error` 处理。
- 钩子是在 SheetEase 进程内执行的受信任代码，拥有与工具相同的本机权限。不要运行来源不明的钩子库。

## 标准目录

```text
SheetEaseHooks/
├─ hooks.json
├─ README.md
├─ AGENTS.md
├─ checks/
│  ├─ __init__.py
│  └─ item_checks.py
└─ shared/
   ├─ __init__.py
   └─ constants.py
```

只有 `hooks.json` 中明确登记且启用的入口会运行。辅助 `.py` 文件不会被误当成检查器执行，因此可以自由拆分子目录和公共模块。

## hooks.json

```json
{
  "api_version": 1,
  "checks": [
    {
      "name": "物品价格检查",
      "entry": "checks.item_checks:check_item_price",
      "order": 100,
      "enabled": true
    }
  ]
}
```

- `api_version`：必须为 `1`，用于阻止不兼容的钩子静默运行。
- `entry`：格式为 `Python模块路径:函数名`。
- `name`：日志中显示的稳定名称；建议使用清楚的中文业务名。
- `order`：整数，越小越先执行；相同值按清单中的先后顺序执行。
- `enabled`：可选，默认 `true`。临时停用时应显式改为 `false`。

也可以用字符串简写：`"checks.item_checks:check_item_price"`。

## 检查函数

```python
def check_item_price(context):
    sheet = context.get_sheet("Item")
    if sheet is None:
        return context.error("ITEM_SHEET_MISSING", "缺少 Item 配置表")

    issues = []
    for row in sheet.rows:
        if row.get("Price", 0) < 0:
            issues.append(context.error(
                "ITEM_PRICE_NEGATIVE",
                "物品价格不能小于 0",
                file=sheet.source_file,
                sheet=sheet.name,
                row=row.excel_row,
                field="Price",
                suggestion="将价格改为大于或等于 0 的整数",
            ))
    return issues
```

函数可以返回 `None`、单个 `HookIssue`，或 `HookIssue` 的可迭代对象（包括使用 `yield` 的生成器）。

## 只读上下文 API（v1）

`context` 提供：

- `api_version`：当前钩子 API 版本；
- `source_root`、`hook_root`：绝对路径对象；
- `sheets`：以 Sheet 名为键的只读映射；
- `config`：本次导出参数的只读映射；
- `get_sheet(name)`：表不存在时返回 `None`；
- `require_sheet(name)`：表不存在时抛出 `KeyError`；
- `error()`、`warning()`、`info()`：创建结构化问题。

每个 `HookSheet` 包含 `name`、`source_file`、`fields`、`rows` 和 `find_by_id(value)`。每个 `HookRow` 包含 `key`、`excel_row`、只读 `values`，并支持 `row["Field"]` 与 `row.get("Field")`。

导出数据中的 `list` 会以只读 `tuple` 暴露，`dict` 会以只读映射暴露。钩子不得依赖修改这些对象。

## 可靠性规范

1. 每条规则使用全工程唯一、长期稳定的错误码，如 `ECONOMY_SHOP_PRICE_NEGATIVE`。
2. 所有业务错误都返回 `HookIssue`；不要用异常表达普通配置错误。
3. 尽量填写 `file/sheet/row/field`，让策划能直接定位 Excel 单元格。
4. 检查器不得写文件、改 Excel、访问网络、弹窗或调用 GUI。
5. 不依赖检查器之间共享的可变全局状态；执行顺序只用于日志和成本控制。
6. 单个检查器只负责一个清晰主题；复杂逻辑下沉到 `shared/`。
7. 遍历表时优先建立局部索引，避免在双重循环中反复全表扫描。
8. 钩子环境保证 Python 标准库和 SheetEase Hook API，不保证任意第三方包存在。
9. 修改钩子后先在 GUI 路径状态中确认“已加载 N 个检查”，再用合法和非法数据分别验证。

## 兼容导入

钩子可以直接使用公开类型：

```python
from ExcelExportTool.hooks import HookContext, HookIssue
```

不要导入 `ExcelExportTool.core`、`parsing` 等内部实现。只有 `ExcelExportTool.hooks` 中公开的 API 承诺按版本管理。

## 发布前检查表

- `hooks.json` 是合法 UTF-8 JSON，入口可加载，顺序明确；
- 错误码不重复，错误信息能让非开发人员理解；
- 合法数据不产生误报，非法数据能稳定阻止导出；
- 缺表、空表、空字段、默认值和容器字段已有防御性处理；
- 没有写文件、联网或修改上下文；
- README 已记录规则目的、负责人和例外策略。
