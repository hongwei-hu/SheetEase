@echo off
setlocal

REM Build SheetEase executable with PyInstaller
where pyinstaller >nul 2>nul
if errorlevel 1 (
  echo [Error] pyinstaller not found. Please install Python and run: pip install pyinstaller
  exit /b 1
)

set ENTRY=ExcelExportTool/app_main.py
set NAME=SheetEase
set RUNTIME_TMP=%LOCALAPPDATA%\SheetEase\_runtime
if not exist "%RUNTIME_TMP%" mkdir "%RUNTIME_TMP%"
set WORKPATH=build
set DISTPATH=dist
set SPECPATH=.

REM Common flags to ensure all submodules are collected and build is clean
set COMMON_FLAGS=--noconsole --clean --noconfirm ^
  --runtime-tmpdir "%RUNTIME_TMP%" ^
  --workpath "%WORKPATH%" ^
  --distpath "%DISTPATH%" ^
  --specpath "%SPECPATH%" ^
  --collect-submodules ExcelExportTool ^
  --hidden-import ExcelExportTool ^
  --hidden-import ExcelExportTool.core.export_process ^
  --hidden-import ExcelExportTool.core.worksheet_data ^
  --hidden-import ExcelExportTool.generation.cs_generation ^
  --hidden-import ExcelExportTool.parsing.data_processing ^
  --hidden-import ExcelExportTool.parsing.excel_processing ^
  --hidden-import ExcelExportTool.utils.type_utils ^
  --hidden-import ExcelExportTool.utils.naming_config ^
  --hidden-import ExcelExportTool.utils.naming_utils ^
  --hidden-import ExcelExportTool.utils.log ^
  --hidden-import ExcelExportTool.exceptions ^
  --hidden-import jinja2 ^
  --hidden-import markupsafe

REM Optionally include ProjectFolder as runtime data (for interface/type checks)
set DATA_FLAGS=--add-data "ProjectFolder;ProjectFolder" ^
  --add-data "ExcelExportTool;ExcelExportTool" ^
  --add-data "docs;docs"

if /I "%1"=="--dir" (
  set BUILD_MODE=dir
) else (
  set BUILD_MODE=onefile
)

echo Building mode: %BUILD_MODE%
echo Runtime tmpdir: %RUNTIME_TMP%
echo Work path: %WORKPATH%
echo Dist path: %DISTPATH%

call :run_build %BUILD_MODE%
if errorlevel 1 (
  echo [Warn] First build attempt failed. Retrying once with clean intermediates...
  if exist "%WORKPATH%\%NAME%" rmdir /s /q "%WORKPATH%\%NAME%"
  if exist "%SPECPATH%\%NAME%.spec" del /f /q "%SPECPATH%\%NAME%.spec"
  call :run_build %BUILD_MODE%
  if errorlevel 1 (
    echo [Error] Build failed after retry.
    exit /b 1
  )
)

echo Build finished. Check the dist folder.
echo Usage: .\build_windows.bat [--dir^|--onefile]
endlocal
exit /b 0

:run_build
if /I "%1"=="dir" (
  pyinstaller %COMMON_FLAGS% %DATA_FLAGS% --name %NAME% "%ENTRY%"
) else (
  pyinstaller %COMMON_FLAGS% %DATA_FLAGS% --onefile --name %NAME% "%ENTRY%"
)
exit /b %errorlevel%
