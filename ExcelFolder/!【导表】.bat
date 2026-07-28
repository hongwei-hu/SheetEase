@echo off
setlocal EnableExtensions
chcp 65001 >nul

rem 选择 Python 启动器
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

rem 批处理所在目录（与 sheet_config.json 同目录）
set "HERE=%~dp0"

rem 切换到项目根，保证包导入正常
pushd "..\"

%PY% -m ExcelExportTool.export_all --config "%HERE%sheet_config.json"
set "rc=%ERRORLEVEL%"

popd
if not "%rc%"=="0" echo [Error] 导表失败，退出码: %rc%
pause
exit /b %rc%
