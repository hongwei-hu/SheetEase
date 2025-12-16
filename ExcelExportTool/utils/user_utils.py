# Author: huhongwei 306463233@qq.com
# MIT License
"""
用户交互工具模块：提供统一的用户确认等功能。
"""
import os


def user_confirm(msg: str, title: str = "用户确认") -> bool:
    """
    统一的用户确认函数：命令行用input，GUI用弹窗。
    返回True表示继续，False表示取消。
    """
    if os.environ.get('SHEETEASE_GUI', '') == '1':
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk._default_root or tk.Tk()
            root.withdraw()
            res = messagebox.askyesno(title, msg)
            return bool(res)
        except Exception:
            print(msg)
            ans = input().strip().lower()
            return ans in ("y", "yes")
    else:
        print(msg)
        ans = input().strip().lower()
        return ans in ("y", "yes")

