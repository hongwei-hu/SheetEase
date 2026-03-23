#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SheetEase 独立启动入口：
- 首次启动：检查当前目录是否存在 sheet_config.json，不存在则弹出最简配置 GUI 让用户填写并保存。
- 后续启动：读取并校验配置，合法则直接执行导表（与现有流程一致）。
- 设计为 PyInstaller 打包入口（可 --onefile）。
"""

import json
import os
import sys
import time
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
import re
import contextlib

# 让 PyInstaller 静态分析到这些模块（即使运行时用兜底方式导入）
try:  # noqa: F401
    from ExcelExportTool.core import export_process as _ep_collect  # type: ignore
    from ExcelExportTool.generation import cs_generation as _cg_collect  # type: ignore
    from ExcelExportTool.core import worksheet_data as _wd_collect  # type: ignore
    from ExcelExportTool.parsing import data_processing as _dp_collect  # type: ignore
    from ExcelExportTool.parsing import excel_processing as _xp_collect  # type: ignore
    from ExcelExportTool.utils import type_utils as _tu_collect  # type: ignore
    from ExcelExportTool.utils import naming_config as _nc_collect  # type: ignore
    from ExcelExportTool.utils import naming_utils as _nu_collect  # type: ignore
    from ExcelExportTool.utils import log as _log_collect  # type: ignore
    from ExcelExportTool import exceptions as _ex_collect  # type: ignore
except Exception:  # 在开发环境无影响
    _ep_collect = None  # type: ignore
    _cg_collect = None  # type: ignore
    _wd_collect = None  # type: ignore
    _dp_collect = None  # type: ignore
    _xp_collect = None  # type: ignore
    _tu_collect = None  # type: ignore
    _nc_collect = None  # type: ignore
    _nu_collect = None  # type: ignore
    _log_collect = None  # type: ignore
    _ex_collect = None  # type: ignore

# 兼容被 PyInstaller 打包后的运行目录
def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


APP_DIR = get_app_dir()
# 确保可导入包路径（开发与打包场景都兼容）
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(APP_DIR / 'ExcelExportTool') not in sys.path:
    sys.path.insert(0, str(APP_DIR / 'ExcelExportTool'))

try:
    from ExcelExportTool.utils.config_io import get_config_file, load_initial_config, save_config  # type: ignore
except Exception:
    from utils.config_io import get_config_file, load_initial_config, save_config  # type: ignore


def _import_batch_excel_to_json():
    """稳健导入 batch_excel_to_json，兼容打包与源码运行。"""
    try:
        from ExcelExportTool.core.export_process import batch_excel_to_json  # type: ignore
        return batch_excel_to_json
    except Exception:
        # 尝试相对导入（当作为包运行时）
        try:
            from .export_process import batch_excel_to_json  # type: ignore
            return batch_excel_to_json
        except Exception:
            # 最后尝试通过 _MEIPASS 或手动补充路径
            import importlib, importlib.util
            base = getattr(sys, '_MEIPASS', None)
            if base:
                # 确保 _MEIPASS 与其中的 ExcelExportTool 在 sys.path 中
                if base not in sys.path:
                    sys.path.insert(0, base)
                xdir = os.path.join(base, 'ExcelExportTool')
                if os.path.isdir(xdir) and xdir not in sys.path:
                    sys.path.insert(0, xdir)
            # 再次尝试包导入
            try:
                return importlib.import_module('ExcelExportTool.export_process').batch_excel_to_json
            except Exception:
                # 直接从文件路径加载作为兜底，并赋予包上下文，支持相对导入
                # 优先 _MEIPASS 下的 ExcelExportTool/export_process.py
                candidates = []
                if base:
                    candidates.append(os.path.join(base, 'ExcelExportTool', 'export_process.py'))
                candidates.append(os.path.join(os.path.dirname(__file__), 'export_process.py'))
                ep_path = next((p for p in candidates if os.path.isfile(p)), None)
                if not ep_path:
                    raise ImportError('export_process.py not found in expected locations')
                fqmn = 'ExcelExportTool.export_process'
                spec = importlib.util.spec_from_file_location(fqmn, ep_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = 'ExcelExportTool'
                    sys.modules[fqmn] = mod
                    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                    return getattr(mod, 'batch_excel_to_json')
                raise ImportError('Failed to load export_process module spec')
CONFIG_FILE = get_config_file(APP_DIR)


def _is_writable_dir(p: str) -> bool:
    try:
        if not p or not os.path.isdir(p):
            return False
        testfile = Path(p) / '.sheet_conf_test.tmp'
        with open(testfile, 'w', encoding='utf-8') as f:
            f.write('ok')
        testfile.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def validate_config(cfg: dict) -> tuple[bool, str]:
    required = ['excel_root', 'output_project', 'cs_output', 'enum_output']
    for k in required:
        if k not in cfg:
            return False, f'配置缺少字段: {k}'
    if not os.path.isdir(cfg['excel_root']):
        return False, f"Excel 根目录不存在: {cfg['excel_root']}"
    for k in ['output_project', 'cs_output', 'enum_output']:
        if not os.path.isdir(cfg[k]):
            # 尝试创建
            try:
                os.makedirs(cfg[k], exist_ok=True)
            except Exception:
                return False, f"无法创建输出目录: {cfg[k]}"
        if not _is_writable_dir(cfg[k]):
            return False, f"输出目录不可写: {cfg[k]}"
    return True, ''


class TextRedirector:
    """Redirects stdout/stderr to a Tk Text widget with ANSI color support."""
    ANSI_RE = re.compile(r"\x1b\[(\d+)m")

    KEYWORDS = (
        '开始导表', '结束', '成功', '失败', '错误', '警告', '完成',
        '引用检查', '收集枚举', '导出', '跳过'
    )

    def __init__(self, text: tk.Text, show_key_only_getter=None, summary_callback=None):
        self.text = text
        self._current_tag = 'ansi-normal'
        self._show_key_only_getter = show_key_only_getter
        self._summary_callback = summary_callback

    def _is_key_line(self, data: str) -> bool:
        if not data:
            return False
        plain = self.ANSI_RE.sub('', data)
        return any(k in plain for k in self.KEYWORDS)

    def write(self, data: str):
        if not data:
            return
        # Normalize newlines and handle CR
        data = data.replace('\r\n', '\n').replace('\r', '\n')

        def _apply_insert(chunk: str, tag: str):
            if not chunk:
                return
            self.text.insert(tk.END, chunk, (tag,))
            self.text.see(tk.END)

        def _process():
            if self._summary_callback:
                try:
                    self._summary_callback(data)
                except Exception:
                    pass
            if self._show_key_only_getter and self._show_key_only_getter() and not self._is_key_line(data):
                return
            pos = 0
            for m in self.ANSI_RE.finditer(data):
                start, end = m.span()
                code = m.group(1)
                _apply_insert(data[pos:start], self._current_tag)
                self._current_tag = self._tag_for_code(code)
                pos = end
            _apply_insert(data[pos:], self._current_tag)
        # marshal to UI thread
        try:
            self.text.after(0, _process)
        except (tk.TclError, RuntimeError):
            # 窗口已关闭或其他GUI错误，静默处理
            pass

    def flush(self):
        pass

    @staticmethod
    def _tag_for_code(code: str) -> str:
        try:
            c = int(code)
        except Exception:
            return 'ansi-normal'
        if c in (0,):
            return 'ansi-normal'
        if c in (31, 91):
            return 'ansi-red'
        if c in (32, 92):
            return 'ansi-green'
        if c in (33, 93):
            return 'ansi-yellow'
        return 'ansi-normal'


class MainWindow:
    def __init__(self, master, init_cfg: dict | None = None):
        self.master = master
        master.title('SheetEase - 导表工具')
        master.geometry('600x400')
        master.minsize(400, 250)

        # Config vars (支持 StringVar 和 BooleanVar)
        self.vars: dict[str, tk.Variable] = {
            'excel_root': tk.StringVar(value=(init_cfg or {}).get('excel_root', '')),
            'output_project': tk.StringVar(value=(init_cfg or {}).get('output_project', '')),
            'cs_output': tk.StringVar(value=(init_cfg or {}).get('cs_output', '')),
            'enum_output': tk.StringVar(value=(init_cfg or {}).get('enum_output', '')),
            'show_key_logs': tk.BooleanVar(value=bool((init_cfg or {}).get('ui', {}).get('show_key_logs', True)) if isinstance((init_cfg or {}).get('ui', {}), dict) else True),
        }
        self._recent_paths: dict[str, list[str]] = dict((init_cfg or {}).get('recent_paths', {})) if isinstance((init_cfg or {}).get('recent_paths', {}), dict) else {}
        self._settings_window: tk.Toplevel | None = None
        self._settings_notebook: ttk.Notebook | None = None
        self._tooltip: tk.Toplevel | None = None
        ui_cfg = (init_cfg or {}).get('ui', {}) if isinstance((init_cfg or {}).get('ui', {}), dict) else {}
        self._last_export_time: str = str(ui_cfg.get('last_export_time', '') or '')
        self._last_export_elapsed: str = str(ui_cfg.get('last_export_elapsed', '') or '')

        # Layout root
        master.grid_rowconfigure(2, weight=1)
        master.grid_columnconfigure(0, weight=1)

        # UI refs
        self.path_inputs: dict[str, ttk.Combobox] = {}
        self.path_status_labels: dict[str, tk.Label] = {}
        self.count_labels: dict[str, tk.Label] = {}

        # 顶部菜单：基础配置与 YooAsset 收集设置放入菜单页签
        self._build_menu()

        # 核心操作区：突出开始导出，右侧放常用勾选项
        header = tk.Frame(master, padx=12, pady=10)
        header.grid(row=0, column=0, sticky='we')
        header.grid_columnconfigure(2, weight=1)

        self.vars['auto_run'] = tk.BooleanVar(value=bool((init_cfg or {}).get('auto_run', False)))
        self.btn_run = tk.Button(
            header,
            text='开始导出',
            command=self.on_run,
            bg='#2f855a',
            fg='white',
            activebackground='#276749',
            relief='flat',
            padx=36,
            pady=12,
            font=('Segoe UI', 13, 'bold'),
        )
        self.btn_run.grid(row=0, column=0, rowspan=2, padx=(0, 18), sticky='w')
        # 常驻高级选项：保留资产严格校验模式，不折叠
        self._advanced_visible = False
        yoo = (init_cfg or {}).get('yooasset', {}) if isinstance((init_cfg or {}).get('yooasset', {}), dict) else {}
        self.vars['yooasset.collector_setting'] = tk.StringVar(value=yoo.get('collector_setting', ''))
        self.vars['yooasset.strict'] = tk.BooleanVar(value=bool(yoo.get('strict', False)))

        option_frame = tk.Frame(header)
        option_frame.grid(row=0, column=1, rowspan=2, sticky='w')
        self.chk_auto = tk.Checkbutton(option_frame, text='打开时自动导表', variable=self.vars['auto_run'])
        self.chk_auto.grid(row=0, column=0, sticky='w')
        self.chk_strict = tk.Checkbutton(option_frame, text='资产校验严格模式（失败中断）', variable=self.vars['yooasset.strict'])
        self.chk_strict.grid(row=1, column=0, sticky='w')
        self.btn_strict_info = tk.Label(option_frame, text='(i)', fg='#2b6cb0', cursor='hand2')
        self.btn_strict_info.grid(row=1, column=1, sticky='w', padx=(6, 0))
        self.btn_strict_example = tk.Button(
            option_frame,
            text='查看示例',
            relief='flat',
            fg='#2b6cb0',
            activeforeground='#1f4e8a',
            activebackground=option_frame.cget('bg'),
            bg=option_frame.cget('bg'),
            bd=0,
            highlightthickness=0,
            cursor='hand2',
            padx=0,
            pady=0,
            command=self._show_strict_examples,
        )
        self.btn_strict_example.grid(row=1, column=2, sticky='w', padx=(10, 0))
        self.btn_strict_info.bind('<Enter>', lambda _e: self._show_strict_tooltip())
        self.btn_strict_info.bind('<Leave>', lambda _e: self._hide_strict_tooltip())

        # 日志工具栏 + 日志区
        log_toolbar = tk.Frame(master, padx=12)
        log_toolbar.grid(row=1, column=0, sticky='we')
        tk.Checkbutton(log_toolbar, text='仅显示关键日志', variable=self.vars['show_key_logs']).pack(side='left')
        self.btn_clear = tk.Button(log_toolbar, text='清空日志', command=self.on_clear)
        self.btn_clear.pack(side='left', padx=(10, 0))

        self.log = scrolledtext.ScrolledText(
            master,
            wrap='word',
            height=14,
            bg='#111111',
            fg='#f5f5f5',
            insertbackground='#f5f5f5',
            font=('Consolas', 10),
        )
        self.log.grid(row=2, column=0, sticky='nsew', padx=12, pady=(0, 6))
        master.grid_rowconfigure(2, weight=1)

        # 底部状态栏（置于日志区域下方）
        self.status_separator = tk.Frame(master, height=1, bg='#dddddd')
        self.status_separator.grid(row=3, column=0, sticky='we', padx=12, pady=(0, 4))

        self.summary_frame = tk.Frame(master, padx=12)
        self.summary_frame.grid(row=4, column=0, sticky='we', pady=(0, 8))
        self.summary_text = tk.StringVar(value='状态：待运行')
        tk.Label(self.summary_frame, textvariable=self.summary_text, fg='#555555').pack(side='left')
        self.snapshot_text = tk.StringVar(value='')
        tk.Label(self.summary_frame, text='  |  ', fg='#999999').pack(side='left')
        tk.Label(self.summary_frame, textvariable=self.snapshot_text, fg='#666666').pack(side='left')

        # Configure ANSI color tags
        self.log.tag_config('ansi-normal', foreground='#f5f5f5')
        self.log.tag_config('ansi-red', foreground='#ff5555')
        self.log.tag_config('ansi-green', foreground='#50fa7b')
        self.log.tag_config('ansi-yellow', foreground='#f1fa8c')
        self.logger = TextRedirector(self.log, show_key_only_getter=lambda: bool(self.vars['show_key_logs'].get()), summary_callback=self._update_summary_from_log)

        # state
        self._running = False
        # 绑定窗口关闭事件：若勾选“自动运行导表”，关闭时自动保存配置
        try:
            self.master.protocol('WM_DELETE_WINDOW', self.on_close)
        except Exception:
            pass
        # 若启用自动运行，则窗口初始化后触发一次导表
        if self.vars['auto_run'].get():
            self.master.after(300, self._autorun_if_enabled)
        # 初始化统计
        try:
            self._refresh_counts()
        except Exception:
            pass
        self._refresh_snapshot()
        self._bind_snapshot_traces()

    def _build_menu(self):
        menubar = tk.Menu(self.master)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label='基础配置', command=lambda: self._open_settings_dialog('basic'))
        settings_menu.add_command(label='YooAsset 收集设置', command=lambda: self._open_settings_dialog('yooasset'))
        settings_menu.add_separator()
        settings_menu.add_command(label='保存配置', command=self.on_save)
        menubar.add_cascade(label='设置', menu=settings_menu)
        self.master.config(menu=menubar)

    def _open_settings_dialog(self, tab: str = 'basic'):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.deiconify()
            self._settings_window.lift()
            self._select_settings_tab(tab)
            return

        win = tk.Toplevel(self.master)
        win.title('配置')
        win.transient(self.master)
        win.geometry('980x520')
        win.minsize(860, 460)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        notebook = ttk.Notebook(win)
        notebook.grid(row=0, column=0, sticky='nsew', padx=12, pady=12)
        self._settings_notebook = notebook

        basic_tab = tk.Frame(notebook)
        basic_tab.grid_columnconfigure(1, weight=1)
        notebook.add(basic_tab, text='基础配置')
        self._add_row(basic_tab, 0, 'Excel 根目录', 'excel_root')
        self._add_count_label(basic_tab, 1, 'excel_root')
        self._add_row(basic_tab, 2, '工程 JSON 输出目录', 'output_project')
        self._add_count_label(basic_tab, 3, 'output_project')
        self._add_row(basic_tab, 4, 'C# 脚本输出目录', 'cs_output')
        self._add_count_label(basic_tab, 5, 'cs_output')
        self._add_row(basic_tab, 6, '枚举输出目录', 'enum_output')
        self._add_count_label(basic_tab, 7, 'enum_output')

        yoo_tab = tk.Frame(notebook)
        yoo_tab.grid_columnconfigure(1, weight=1)
        notebook.add(yoo_tab, text='YooAsset')
        self._add_file_row(yoo_tab, 0, 'YooAsset CollectorSetting.asset', 'yooasset.collector_setting')
        tk.Label(yoo_tab, text='提示：严格校验开关已移至主界面。', fg='#666666').grid(row=1, column=0, columnspan=4, sticky='w', pady=(4, 0))

        btns = tk.Frame(win)
        btns.grid(row=1, column=0, sticky='e', padx=12, pady=(0, 12))
        tk.Button(btns, text='测试路径可用性', command=self._run_path_health_check).pack(side='left', padx=(0, 6))
        tk.Button(btns, text='保存配置', command=self.on_save).pack(side='left', padx=(0, 6))
        tk.Button(btns, text='关闭', command=win.destroy).pack(side='left')

        status_bar = tk.Frame(win)
        status_bar.grid(row=2, column=0, sticky='we', padx=12, pady=(0, 12))
        self.settings_status_text = tk.StringVar(value=self._settings_status_text())
        tk.Label(status_bar, textvariable=self.settings_status_text, fg='#666666').pack(side='left')

        def _on_close():
            self._settings_window = None
            self._settings_notebook = None
            # 配置弹窗关闭后清理控件引用，避免后续访问已销毁的 Tk 组件。
            self.path_inputs.clear()
            self.path_status_labels.clear()
            self.count_labels.clear()
            win.destroy()

        win.protocol('WM_DELETE_WINDOW', _on_close)
        self._settings_window = win
        self._select_settings_tab(tab)
        try:
            self._refresh_counts()
        except Exception:
            pass

    def _select_settings_tab(self, tab: str):
        if not self._settings_notebook:
            return
        tabs = self._settings_notebook.tabs()
        if not tabs:
            return
        index = 0 if tab == 'basic' else 1
        if index < len(tabs):
            self._settings_notebook.select(tabs[index])

    def _show_strict_tooltip(self):
        self._hide_strict_tooltip()
        tip = tk.Toplevel(self.master)
        tip.wm_overrideredirect(True)
        x = self.btn_strict_info.winfo_rootx() + 16
        y = self.btn_strict_info.winfo_rooty() + 20
        tip.wm_geometry(f'+{x}+{y}')
        msg = (
            '严格模式：任一 [Asset] 字段校验失败将中断导出。\n'
            '关闭严格模式：失败仅记录警告并继续导出。\n\n'
            '收集设置路径请在「设置 -> YooAsset 收集设置」中配置：\n'
            '通常指向 Unity 工程中的 CollectorSetting.asset 文件。'
        )
        tk.Label(tip, text=msg, justify='left', bg='#fffbe6', fg='#333333',
                 relief='solid', bd=1, padx=8, pady=6).pack()
        self._tooltip = tip

    def _show_strict_examples(self):
        msg = (
            '常见 [Asset] 标注示例：\n'
            '1) [Asset]icon_name\n'
            '2) [Asset:prefab]hero_prefab\n'
            '3) list(string) + [Asset:sprite]icon_list\n\n'
            'CollectorSetting 路径建议：\n'
            '- Unity项目/Assets/.../CollectorSetting.asset\n'
            '- 在「设置 -> YooAsset 收集设置」中选择该 asset 文件\n\n'
            '严格模式开启：任一资源未找到即中断导出。\n'
            '严格模式关闭：记录警告并继续导出。'
        )
        try:
            messagebox.showinfo('严格校验示例', msg)
        except Exception:
            pass

    def _hide_strict_tooltip(self):
        if self._tooltip:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def _build_cfg(self) -> dict:
        return {
            'excel_root': self.vars['excel_root'].get().strip(),
            'output_project': self.vars['output_project'].get().strip(),
            'cs_output': self.vars['cs_output'].get().strip(),
            'enum_output': self.vars['enum_output'].get().strip(),
            'auto_run': bool(self.vars['auto_run'].get()),
            'recent_paths': self._recent_paths,
            'ui': {
                'show_advanced': bool(self._advanced_visible),
                'show_key_logs': bool(self.vars['show_key_logs'].get()),
                'last_export_time': self._last_export_time,
                'last_export_elapsed': self._last_export_elapsed,
            },
            'yooasset': {
                'collector_setting': self.vars['yooasset.collector_setting'].get().strip(),
                'strict': bool(self.vars['yooasset.strict'].get()),
            }
        }

    def _settings_status_text(self) -> str:
        t = self._last_export_time or '从未成功导出'
        e = self._last_export_elapsed or '-'
        return f'上次成功导出：{t}    上次耗时：{e}'

    def _bind_snapshot_traces(self):
        keys = ['excel_root', 'output_project', 'cs_output', 'enum_output', 'yooasset.strict']
        for k in keys:
            try:
                self.vars[k].trace_add('write', lambda *_args: self._refresh_snapshot())
            except Exception:
                pass

    def _refresh_snapshot(self):
        def _name_of(key: str) -> str:
            raw = str(self.vars[key].get() or '').strip()
            if not raw:
                return '未配置'
            return Path(raw).name or raw

        strict_mode = '开' if bool(self.vars['yooasset.strict'].get()) else '关'
        text = (
            f"配置快照：Excel[{_name_of('excel_root')}] 输出[{_name_of('output_project')}] "
            f"脚本[{_name_of('cs_output')}] 枚举[{_name_of('enum_output')}] 严格[{strict_mode}]"
        )
        self.snapshot_text.set(text)

    def _run_path_health_check(self):
        cfg = self._build_cfg()
        errors: list[str] = []
        warnings: list[str] = []

        ok, msg = validate_config(cfg)
        if not ok:
            errors.append(msg)

        excel_root = Path(cfg.get('excel_root', '')) if cfg.get('excel_root') else None
        if not excel_root or not excel_root.is_dir():
            errors.append('Excel 根目录不存在或不可访问')
        else:
            count = self._safe_count(
                f for f in excel_root.rglob('*.xlsx')
                if f.name and f.name[0].isupper() and not f.name.startswith('~$')
            )
            if count <= 0:
                warnings.append('Excel 目录中没有符合导出规则的 .xlsx 文件')

        cs_output = cfg.get('cs_output', '')
        enum_output = cfg.get('enum_output', '')
        if not self._is_under_assets(cs_output):
            warnings.append('C# 输出目录不在 Unity Assets 子目录')
        if not self._is_under_assets(enum_output):
            warnings.append('枚举输出目录不在 Unity Assets 子目录')

        collector = cfg.get('yooasset', {}).get('collector_setting', '') if isinstance(cfg.get('yooasset', {}), dict) else ''
        if collector:
            cp = Path(collector)
            if not cp.exists():
                errors.append('YooAsset CollectorSetting 路径不存在')
            elif cp.suffix.lower() != '.asset':
                warnings.append('YooAsset CollectorSetting 不是 .asset 文件')
            else:
                try:
                    with open(cp, 'rb') as _fp:
                        _fp.read(1)
                except Exception:
                    errors.append('YooAsset CollectorSetting 文件不可读')
        else:
            warnings.append('未配置 YooAsset CollectorSetting（将跳过资产校验）')

        if errors:
            details = '\n'.join([f'- {x}' for x in errors] + [f'- {x}' for x in warnings])
            messagebox.showerror('路径健康检查失败', details)
            return

        details = '\n'.join([f'- {x}' for x in warnings]) if warnings else '所有路径检查通过。'
        messagebox.showinfo('路径健康检查', details)

    def _toggle_advanced(self):
        # 兼容旧配置字段，当前版本不再提供折叠高级区。
        self._advanced_visible = False

    def _refresh_advanced_toggle_text(self):
        # 兼容保留方法：当前布局不需要更新按钮文本。
        return

    @staticmethod
    def _open_path(path: str):
        if not path:
            return
        try:
            p = Path(path)
            target = p if p.is_dir() else p.parent
            if os.name == 'nt':
                os.startfile(str(target))  # type: ignore[attr-defined]
        except Exception:
            pass

    def _record_recent_path(self, key: str, value: str):
        value = (value or '').strip()
        if not value:
            return
        if key not in self._recent_paths:
            self._recent_paths[key] = []
        items = [v for v in self._recent_paths[key] if v != value]
        self._recent_paths[key] = [value] + items[:7]
        cb = self.path_inputs.get(key)
        if cb:
            try:
                if cb.winfo_exists():
                    cb.configure(values=self._recent_paths.get(key, []))
                else:
                    self.path_inputs.pop(key, None)
            except tk.TclError:
                self.path_inputs.pop(key, None)

    def _status_for(self, key: str, path: str, detail_color: str) -> tuple[str, str]:
        if not path:
            return '未配置', '#999999'
        if detail_color == '#ff5555':
            return '需处理', '#ff5555'
        return '可用', '#2f855a'

    def _add_row(self, parent: tk.Misc, row: int, label: str, key: str):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=4)
        cb = ttk.Combobox(parent, textvariable=self.vars[key], values=self._recent_paths.get(key, []))
        cb.grid(row=row, column=1, sticky='we', padx=(0, 8), pady=4)
        self.path_inputs[key] = cb

        def browse():
            cur = self.vars[key].get()
            initd = cur if os.path.isdir(cur) else str(APP_DIR)
            p = filedialog.askdirectory(initialdir=initd)
            if p:
                self.vars[key].set(p)

        tk.Button(parent, text='浏览', command=browse).grid(row=row, column=2, padx=(0, 6), pady=4)
        tk.Button(parent, text='打开', command=lambda k=key: self._open_path(self.vars[k].get())).grid(row=row, column=3, padx=(0, 2), pady=4)
        status = tk.Label(parent, text='未配置', width=8, anchor='center', fg='#999999')
        status.grid(row=row, column=4, padx=(8, 0), pady=4)
        self.path_status_labels[key] = status

        # 路径变化时刷新统计
        try:
            self.vars[key].trace_add('write', lambda *_, k=key: self._on_path_changed(k))
        except Exception:
            pass

        cb.bind('<<ComboboxSelected>>', lambda *_ , k=key: self._on_path_changed(k))

    def _on_path_changed(self, key: str):
        self._refresh_count_for(key)

    def _record_core_recent_paths(self):
        for key in ['excel_root', 'output_project', 'cs_output', 'enum_output']:
            self._record_recent_path(key, str(self.vars[key].get()))

    def _add_file_row(self, parent: tk.Misc, row: int, label: str, key: str):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=4)
        e = tk.Entry(parent, textvariable=self.vars[key])
        e.grid(row=row, column=1, sticky='we', padx=(0, 8), pady=4)

        def browse_file():
            cur = self.vars[key].get()
            initd = os.path.dirname(cur) if os.path.isfile(cur) else (cur if os.path.isdir(cur) else str(APP_DIR))
            p = filedialog.askopenfilename(initialdir=initd, filetypes=[('Unity Asset','*.asset'), ('All Files','*.*')])
            if p:
                self.vars[key].set(p)
        tk.Button(parent, text='选择文件', command=browse_file).grid(row=row, column=2, padx=(0, 6), pady=4)
        tk.Button(parent, text='打开', command=lambda k=key: self._open_path(self.vars[k].get())).grid(row=row, column=3, padx=(0, 2), pady=4)

    def _add_count_label(self, parent: tk.Misc, row: int, key: str):
        lbl = tk.Label(parent, text='', anchor='w', fg='#777777')
        lbl.grid(row=row, column=1, columnspan=4, sticky='w', pady=(0, 4))
        self.count_labels[key] = lbl

    def _refresh_counts(self):
        for k in ['excel_root', 'output_project', 'cs_output', 'enum_output']:
            self._refresh_count_for(k)

    def _refresh_count_for(self, key: str):
        try:
            lbl = self.count_labels.get(key)
            if not lbl:
                return
            path = str(self.vars[key].get())
            text, color = self._count_text_for(key, path)
            lbl.configure(text=text, fg=color)
            st = self.path_status_labels.get(key)
            if st:
                s_text, s_color = self._status_for(key, path, color)
                st.configure(text=s_text, fg=s_color)
        except Exception:
            pass

    def _update_summary_from_log(self, data: str):
        plain = re.sub(r"\x1b\[(\d+)m", '', data)
        if '开始导表' in plain:
            self.summary_text.set('状态：导出中…')
        elif '总耗时' in plain and '成功' in plain:
            self.summary_text.set(f'状态：{plain.strip()}')
        elif '失败' in plain and '导表' in plain:
            self.summary_text.set(f'状态：{plain.strip()}')

    @staticmethod
    def _safe_count(iterator) -> int:
        try:
            return sum(1 for _ in iterator)
        except Exception:
            return 0

    def _count_text_for(self, key: str, path: str) -> tuple[str, str]:
        p = Path(path) if path else None
        normal = '#888888'
        red = '#ff5555'
        if key == 'excel_root':
            n = 0
            try:
                if p and p.is_dir():
                    # .xlsx 且首字母大写且非临时文件(~$)
                    n = self._safe_count(
                        f for f in p.rglob('*.xlsx')
                        if f.name and f.name[0].isupper() and not f.name.startswith('~$')
                    )
            except Exception:
                n = 0
            if not p or not p.is_dir():
                return '目录不存在或不可访问', red
            if n == 0:
                return '表格目录没有任何符合导出规范的表格。命名规则：.xlsx，文件名首字母需大写，不以 ~$ 开头', red
            return (f'该目录将导出{n}张Excel表格', normal)
        elif key == 'output_project':
            n = 0
            try:
                if p and p.is_dir():
                    n = self._safe_count(f for f in p.rglob('*.json'))
            except Exception:
                n = 0
            if not p or not p.exists():
                # 不强制要求存在，导出时会自动创建
                return '该目录包含0个Json文件', normal
            # 简单可写检查
            try:
                if not _is_writable_dir(str(p)):
                    return '输出目录不可写', red
            except Exception:
                pass
            return (f'该目录包含{n}个Json文件', normal)
        elif key in ('cs_output', 'enum_output'):
            n = 0
            try:
                if p and p.is_dir():
                    n = self._safe_count(f for f in p.rglob('*.cs'))
            except Exception:
                n = 0
            # 必须位于 Unity 工程 Assets 子目录
            if not self._is_under_assets(path):
                return '该目录不在 Unity 工程的 Assets 子文件夹内，建议放在 Assets 下', red
            return (f'该目录包含{n}个脚本', normal)
        return ('', normal)

    @staticmethod
    def _is_under_assets(path: str) -> bool:
        try:
            if not path:
                return False
            parts = [s.lower() for s in Path(path).parts]
            return 'assets' in parts
        except Exception:
            return False

    def _strict_validate_for_export(self, cfg: dict) -> tuple[bool, str]:
        """用于开始导表前的严格校验：
        - Excel 目录必须存在且包含至少 1 个符合规范的 .xlsx
        - cs_output 与 enum_output 必须位于 Unity 工程 Assets 子目录
        - 同时复用基础校验（可写、可创建等）
        """
        # 基础校验
        ok, msg = validate_config(cfg)
        if not ok:
            return False, msg
        # Excel 下是否有符合规范的文件
        try:
            p = Path(cfg.get('excel_root', ''))
            n = 0
            if p.is_dir():
                n = self._safe_count(
                    f for f in p.rglob('*.xlsx')
                    if f.name and f.name[0].isupper() and not f.name.startswith('~$')
                )
            if n <= 0:
                return False, '表格目录没有任何符合导出规范的表格。命名规则：扩展名为 .xlsx，文件名首字母需大写，不以 ~$ 开头'
        except Exception:
            return False, 'Excel 根目录不可访问'
        # Unity Assets 子目录检查
        # Unity Assets 子目录检查 -> 仅作警告，不阻止导出
        warn_msgs = []
        if not self._is_under_assets(cfg.get('cs_output', '')):
            warn_msgs.append('脚本目录建议位于 Unity 工程的 Assets 子目录下')
        if not self._is_under_assets(cfg.get('enum_output', '')):
            warn_msgs.append('枚举目录建议位于 Unity 工程的 Assets 子目录下')
        if warn_msgs:
            try:
                messagebox.showwarning('路径建议', '\n'.join(warn_msgs) + '\n将继续导表。')
            except Exception:
                pass
        return True, ''

    def _set_running_ui(self, running: bool):
        try:
            if running:
                self.btn_run.configure(text='导出中…', state='disabled')
                self.btn_clear.configure(state='disabled')
                self.chk_auto.configure(state='disabled')
                self.chk_strict.configure(state='disabled')
                self.btn_strict_example.configure(state='disabled')
            else:
                self.btn_run.configure(text='开始导出', state='normal')
                self.btn_clear.configure(state='normal')
                self.chk_auto.configure(state='normal')
                self.chk_strict.configure(state='normal')
                self.btn_strict_example.configure(state='normal')
        except Exception:
            pass

    def on_save(self):
        self._record_core_recent_paths()
        cfg = self._build_cfg()
        ok, msg = validate_config(cfg)
        if not ok:
            messagebox.showerror('配置无效', msg)
            return
        try:
            save_config(CONFIG_FILE, cfg)
            if hasattr(self, 'settings_status_text') and self.settings_status_text is not None:
                self.settings_status_text.set(self._settings_status_text())
            messagebox.showinfo('完成', f'已保存配置到 {CONFIG_FILE}')
        except Exception as e:
            messagebox.showerror('保存失败', str(e))

    def on_clear(self):
        try:
            self.log.delete('1.0', tk.END)
        except Exception:
            pass

    def on_close(self):
        """窗口关闭时：若勾选了自动运行导表，则自动保存当前配置。"""
        try:
            # 仅在启用自动运行时执行自动保存
            if 'auto_run' in self.vars and bool(self.vars['auto_run'].get()):
                self._record_core_recent_paths()
                cfg = self._build_cfg()
                # 关闭时的保存不强校验，静默失败即可
                try:
                    save_config(CONFIG_FILE, cfg, silent=True)
                except Exception:
                    pass
        finally:
            try:
                self.master.destroy()
            except Exception:
                pass

    def on_run(self):
        if self._running:
            return
        self._record_core_recent_paths()
        cfg = self._build_cfg()
        # 严格校验：阻止非法配置导出，并给出提示（包含自动导表场景）
        ok, msg = self._strict_validate_for_export(cfg)
        if not ok:
            # 刷新标签颜色，标记错误
            try:
                self._refresh_counts()
            except Exception:
                pass
            messagebox.showerror('配置无效', msg)
            return
        # persist cfg
        try:
            save_config(CONFIG_FILE, cfg, silent=True)
        except Exception:
            pass
        self._running = True
        self._set_running_ui(True)
        self.summary_text.set('状态：准备导出…')
        self._start_export_thread(cfg)

    def _autorun_if_enabled(self):
        try:
            if self.vars['auto_run'].get() and not self._running:
                self.on_run()
        except Exception:
            pass

    def _start_export_thread(self, cfg: dict):
        def target():
            code = 1
            err_message = ''
            elapsed_sec = 0.0
            try:
                # GUI 模式 -> 弹窗确认
                os.environ['SHEETEASE_GUI'] = '1'
                # 透传本次运行配置（供资产校验读取）
                try:
                    os.environ['SHEETEASE_CONFIG_JSON'] = json.dumps(cfg, ensure_ascii=False)
                except Exception:
                    pass
                bexport = _import_batch_excel_to_json()
                # Redirect stdout/stderr into GUI log
                # 注意：TextRedirector 实现了 write 和 flush 方法，符合 IO 协议
                import sys
                old_stdout, old_stderr = sys.stdout, sys.stderr
                sys.stdout = self.logger  # type: ignore
                sys.stderr = self.logger  # type: ignore
                try:
                    started = time.perf_counter()
                    bexport(
                        source_folder=cfg['excel_root'],
                        output_client_folder=None,
                        output_project_folder=cfg['output_project'],
                        csfile_output_folder=cfg['cs_output'],
                        enum_output_folder=cfg['enum_output'],
                        diff_only=True,
                        dry_run=False,
                        auto_cleanup=True,
                    )
                    elapsed_sec = max(0.0, time.perf_counter() - started)
                    code = 0
                finally:
                    sys.stdout, sys.stderr = old_stdout, old_stderr
            except SystemExit as se:
                code = int(getattr(se, 'code', 1) or 0)
            except Exception as e:
                err_message = str(e)
                code = 1
            finally:
                def done():
                    self._running = False
                    self._set_running_ui(False)
                    try:
                        if code == 0:
                            self._last_export_time = time.strftime('%Y-%m-%d %H:%M:%S')
                            self._last_export_elapsed = f'{elapsed_sec:.2f}s'
                            self._refresh_snapshot()
                            if hasattr(self, 'settings_status_text') and self.settings_status_text is not None:
                                self.settings_status_text.set(self._settings_status_text())
                            try:
                                save_config(CONFIG_FILE, self._build_cfg(), silent=True)
                            except Exception:
                                pass
                            messagebox.showinfo('完成', '导表成功')
                        else:
                            messagebox.showerror('失败', err_message or '导表失败，详见日志')
                    except Exception:
                        pass
                self.master.after(0, done)
        threading.Thread(target=target, daemon=True).start()


def run_export_with_cfg(cfg: dict) -> int:
    """保留给可能的 CLI/非 GUI 场景使用；当前 GUI 通过 MainWindow 启动导出。"""
    os.environ['SHEETEASE_GUI'] = '1'
    batch_excel_to_json = _import_batch_excel_to_json()
    batch_excel_to_json(
        source_folder=cfg['excel_root'],
        output_client_folder=None,
        output_project_folder=cfg['output_project'],
        csfile_output_folder=cfg['cs_output'],
        enum_output_folder=cfg['enum_output'],
        diff_only=True,
        dry_run=False,
        auto_cleanup=True,
    )
    return 0


def main():
    # 读取或创建配置
    cfg = load_initial_config(APP_DIR, CONFIG_FILE)
    # 启动统一 GUI（带配置与日志区域）
    root = tk.Tk()
    # 若 cfg 不合法或为空，也仅作为初值展示在窗口内，让用户修正
    if not cfg:
        cfg = {}
    app = MainWindow(root, init_cfg=cfg)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
