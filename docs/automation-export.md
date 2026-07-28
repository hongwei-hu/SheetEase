# 自动化导出与检查

SheetEase 默认仍面向人工使用：双击 `SheetEase.exe` 打开 GUI，双击 `!【导表】.bat` 在控制台显示完整彩色日志并在结束时暂停。自动化调用必须显式传入 `--headless`，因此不会意外弹出窗口或等待输入。

## 推荐入口

表格目录中的 `Invoke-SheetEase.ps1` 封装了稳定参数、报告读取和退出码传递：

```powershell
# 只解析和检查，不写 JSON/C#/枚举，也不清理旧文件（默认）
.\Invoke-SheetEase.ps1

# 执行真实导出；默认仍不做可能需要人工确认的旧文件清理
.\Invoke-SheetEase.ps1 -Mode Export

# 验证部署后的可执行文件也能完成无界面检查
.\Invoke-SheetEase.ps1 -UseExecutable
```

默认报告写入表格目录的 `.sheetease/agent-export-report.json`。可以用 `-ReportPath` 指定每次运行的独立路径。只有明确传入 `-AllowCleanup` 时，自动化真实导出才启用旧产物清理。

## 直接调用 CLI

源码入口与打包程序使用同一套导出管线和参数：

```powershell
python -m ExcelExportTool.export_all `
  --headless `
  --dry-run `
  --no-cleanup `
  --config D:\RgDesign\Excel\sheet_config.json `
  --report D:\RgDesign\Excel\.sheetease\agent-export-report.json

D:\RgDesign\Excel\SheetEase.exe `
  --headless `
  --dry-run `
  --no-cleanup `
  --config D:\RgDesign\Excel\sheet_config.json `
  --report D:\RgDesign\Excel\.sheetease\agent-export-report.json
```

`--dry-run` 会执行表格解析、类型/约束检查、自定义钩子和引用检查，但不写导出产物。`--no-cleanup` 禁用旧文件扫描与删除确认，适合无人值守运行。

## 稳定退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 导出或检查成功 |
| `2` | 参数、配置文件或路径校验失败 |
| `3` | 表格、约束、自定义钩子或导出失败 |
| `4` | 未预期的工具内部错误，或成功后无法写入报告 |
| `130` | 运行被中断 |

不要只搜索控制台中的“成功”文本，应以进程退出码和 JSON 报告的 `status` 为准。

## JSON 报告

报告使用 UTF-8 编码并以原子替换方式写入，顶层字段包括：

- `schema_version`：当前为 `1`，消费方应先检查版本。
- `mode`：`check` 或 `export`。
- `status`、`exit_code`：本次运行的最终状态。
- `started_at`、`finished_at`、`duration_seconds`：UTC 时间与耗时。
- `options`、`config`：实际采用的运行选项和关键路径快照。
- `summary`：成功时的表格数、处理数、产物路径、JSON 大小和钩子问题。
- `error`：失败类型、消息、异常上下文；钩子失败时包含结构化 `issues`。
- `log`：去除 ANSI 颜色码后的完整人类日志，供诊断兜底。

钩子问题会保留 `severity`、`code`、`message`、`file`、`sheet`、`row`、`field` 和 `suggestion`。新增检查规则时应优先依赖这些字段定位问题，不要解析中文日志格式。

## 人工入口兼容性

- 不传 `--headless` 时，`SheetEase.exe` 始终打开原 GUI。
- `!【导表】.bat` 继续实时显示完整控制台日志并在结束时 `pause`。
- 批处理现在会保存并返回 Python 导出进程的真实退出码；失败时额外显示退出码，不改变原日志内容。
- GUI 与自动化模式复用 `batch_excel_to_json`，不会出现两套校验规则逐渐偏离的问题。
