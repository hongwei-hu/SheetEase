# Author: huhongwei 306463233@qq.com
# MIT License
"""
兼容性入口文件：保持向后兼容，允许使用 python -m ExcelExportTool.export_game_client
"""
from .core.export_game_client import main

if __name__ == '__main__':
    main()

