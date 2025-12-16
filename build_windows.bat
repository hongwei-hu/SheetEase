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

REM Common flags to ensure all submodules are collected and build is clean
set COMMON_FLAGS=--noconsole --clean --noconfirm ^
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
  --hidden-import ExcelExportTool.exceptions

REM Optionally include ProjectFolder as runtime data (for interface/type checks)
set DATA_FLAGS=--add-data "ProjectFolder;ProjectFolder" ^
  --add-data "ExcelExportTool;ExcelExportTool"

if "%1"=="--onefile" (
  pyinstaller %COMMON_FLAGS% %DATA_FLAGS% --onefile --name %NAME% "%ENTRY%"
) else (
  pyinstaller %COMMON_FLAGS% %DATA_FLAGS% --name %NAME% "%ENTRY%"
)

echo Build finished. Check the dist folder.
endlocal
