# Author: huhongwei 306463233@qq.com
# MIT License
"""
兼容性入口文件：保持向后兼容，允许使用 python -m ExcelExportTool.export_all
"""
from .core.export_all import main

if __name__ == '__main__':
    main()

