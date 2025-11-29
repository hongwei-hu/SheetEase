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
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import re
import contextlib

# 让 PyInstaller 静态分析到这些模块（即使运行时用兜底方式导入）
try:  # noqa: F401
    from ExcelExportTool import export_process as _ep_collect  # type: ignore
    from ExcelExportTool import cs_generation as _cg_collect  # type: ignore
    from ExcelExportTool import worksheet_data as _wd_collect  # type: ignore
    from ExcelExportTool import data_processing as _dp_collect  # type: ignore
    from ExcelExportTool import excel_processing as _xp_collect  # type: ignore
    from ExcelExportTool import type_utils as _tu_collect  # type: ignore
    from ExcelExportTool import naming_config as _nc_collect  # type: ignore
    from ExcelExportTool import naming_utils as _nu_collect  # type: ignore
    from ExcelExportTool import log as _log_collect  # type: ignore
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


def _import_batch_excel_to_json():
    """稳健导入 batch_excel_to_json，兼容打包与源码运行。"""
    try:
        from ExcelExportTool.export_process import batch_excel_to_json  # type: ignore
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
CONFIG_FILE = APP_DIR / 'sheet_config.json'


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

    def __init__(self, text: tk.Text):
        self.text = text
        self._current_tag = 'ansi-normal'

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
        master.minsize(820, 520)

        # Config vars (支持 StringVar 和 BooleanVar)
        self.vars: dict[str, tk.Variable] = {
            'excel_root': tk.StringVar(value=(init_cfg or {}).get('excel_root', '')),
            'output_project': tk.StringVar(value=(init_cfg or {}).get('output_project', '')),
            'cs_output': tk.StringVar(value=(init_cfg or {}).get('cs_output', '')),
            'enum_output': tk.StringVar(value=(init_cfg or {}).get('enum_output', '')),
        }

        # Layout root
        # 仅让日志区域（最后的日志行）随窗口高度变化，其余区域保持紧凑
        master.grid_rowconfigure(11, weight=1)
        master.grid_columnconfigure(1, weight=1)

        # 统计标签集合
        self.count_labels: dict[str, tk.Label] = {}

        # Config form（每个目录输入行占用偶数行，下一行用于显示统计信息）
        self._add_row(0, 'Excel 根目录:', 'excel_root')
        self._add_count_label(1, 'excel_root')
        self._add_row(2, '工程 JSON 输出目录:', 'output_project')
        self._add_count_label(3, 'output_project')
        self._add_row(4, 'C# 脚本输出目录:', 'cs_output')
        self._add_count_label(5, 'cs_output')
        self._add_row(6, '枚举输出目录:', 'enum_output')
        self._add_count_label(7, 'enum_output')

        # YooAsset 资产校验配置（可选）
        yoo = (init_cfg or {}).get('yooasset', {}) if isinstance((init_cfg or {}).get('yooasset', {}), dict) else {}
        self.vars['yooasset.collector_setting'] = tk.StringVar(value=yoo.get('collector_setting', ''))
        self.vars['yooasset.strict'] = tk.BooleanVar(value=bool(yoo.get('strict', False)))
        self._add_file_row(8, 'YooAsset CollectorSetting.asset:', 'yooasset.collector_setting')
        # 严格模式勾选（失败即中断），建议先关闭，稳定后再开启
        tk.Checkbutton(self.master, text='资产校验严格模式（失败中断）', variable=self.vars['yooasset.strict']).grid(row=9, column=0, columnspan=3, sticky='w', padx=6, pady=(0,6))

        # Buttons
        btn_frame = tk.Frame(master)
        btn_frame.grid(row=10, column=0, columnspan=3, sticky='we', pady=(6, 6))
        self.btn_save = tk.Button(btn_frame, text='保存配置', command=self.on_save)
        self.btn_run = tk.Button(btn_frame, text='开始导出', command=self.on_run)
        self.btn_clear = tk.Button(btn_frame, text='清空日志', command=self.on_clear)
        # 自动运行导表勾选
        self.vars['auto_run'] = tk.BooleanVar(value=bool((init_cfg or {}).get('auto_run', False)))
        self.chk_auto = tk.Checkbutton(btn_frame, text='打开时自动运行导表', variable=self.vars['auto_run'])
        self.btn_save.pack(side='left', padx=4)
        self.btn_run.pack(side='left', padx=4)
        self.btn_clear.pack(side='left', padx=4)
        self.chk_auto.pack(side='left', padx=12)

        # Log area
        self.log = scrolledtext.ScrolledText(master, wrap='word', height=18, bg='#000000', fg='#ffffff')
        self.log.grid(row=11, column=0, columnspan=3, sticky='nsew', padx=6, pady=(0, 6))
        # Configure ANSI color tags
        self.log.tag_config('ansi-normal', foreground='#ffffff')
        self.log.tag_config('ansi-red', foreground='#ff5555')
        self.log.tag_config('ansi-green', foreground='#50fa7b')
        self.log.tag_config('ansi-yellow', foreground='#f1fa8c')
        self.logger = TextRedirector(self.log)

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

    def _add_row(self, row: int, label: str, key: str):
        tk.Label(self.master, text=label).grid(row=row, column=0, sticky='w', padx=6, pady=6)
        e = tk.Entry(self.master, textvariable=self.vars[key])
        e.grid(row=row, column=1, sticky='we', padx=6, pady=6)
        def browse():
            cur = self.vars[key].get()
            initd = cur if os.path.isdir(cur) else str(APP_DIR)
            p = filedialog.askdirectory(initialdir=initd)
            if p:
                self.vars[key].set(p)
        tk.Button(self.master, text='浏览', command=browse).grid(row=row, column=2, padx=6, pady=6)
        # 路径变化时刷新统计
        try:
            self.vars[key].trace_add('write', lambda *_, k=key: self._refresh_count_for(k))
        except Exception:
            pass

    def _add_file_row(self, row: int, label: str, key: str):
        tk.Label(self.master, text=label).grid(row=row, column=0, sticky='w', padx=6, pady=6)
        e = tk.Entry(self.master, textvariable=self.vars[key])
        e.grid(row=row, column=1, sticky='we', padx=6, pady=6)
        def browse_file():
            cur = self.vars[key].get()
            initd = os.path.dirname(cur) if os.path.isfile(cur) else (cur if os.path.isdir(cur) else str(APP_DIR))
            p = filedialog.askopenfilename(initialdir=initd, filetypes=[('Unity Asset','*.asset'), ('All Files','*.*')])
            if p:
                self.vars[key].set(p)
        tk.Button(self.master, text='选择文件', command=browse_file).grid(row=row, column=2, padx=6, pady=6)

    def _add_count_label(self, row: int, key: str):
        lbl = tk.Label(self.master, text='', anchor='w', fg='#888888')
        lbl.grid(row=row, column=0, columnspan=3, sticky='w', padx=6, pady=(0, 6))
        self.count_labels[key] = lbl

    def _refresh_counts(self):
        for k in ['excel_root', 'output_project', 'cs_output', 'enum_output']:
            self._refresh_count_for(k)

    def _refresh_count_for(self, key: str):
        try:
            lbl = self.count_labels.get(key)
            if not lbl:
                return
            text, color = self._count_text_for(key, self.vars[key].get())
            lbl.configure(text=text, fg=color)
        except Exception:
            pass

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

    def on_save(self):
        cfg = {
            'excel_root': self.vars['excel_root'].get().strip(),
            'output_project': self.vars['output_project'].get().strip(),
            'cs_output': self.vars['cs_output'].get().strip(),
            'enum_output': self.vars['enum_output'].get().strip(),
            'auto_run': bool(self.vars['auto_run'].get()),
            'yooasset': {
                'collector_setting': self.vars['yooasset.collector_setting'].get().strip(),
                'strict': bool(self.vars['yooasset.strict'].get()),
            }
        }
        ok, msg = validate_config(cfg)
        if not ok:
            messagebox.showerror('配置无效', msg)
            return
        try:
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
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
                cfg = {
                    'excel_root': self.vars['excel_root'].get().strip(),
                    'output_project': self.vars['output_project'].get().strip(),
                    'cs_output': self.vars['cs_output'].get().strip(),
                    'enum_output': self.vars['enum_output'].get().strip(),
                    'auto_run': bool(self.vars['auto_run'].get()),
                    'yooasset': {
                        'collector_setting': self.vars['yooasset.collector_setting'].get().strip(),
                        'strict': bool(self.vars['yooasset.strict'].get()),
                    }
                }
                # 关闭时的保存不强校验，静默失败即可
                try:
                    CONFIG_FILE.write_text(
                        json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8'
                    )
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
        cfg = {
            'excel_root': self.vars['excel_root'].get().strip(),
            'output_project': self.vars['output_project'].get().strip(),
            'cs_output': self.vars['cs_output'].get().strip(),
            'enum_output': self.vars['enum_output'].get().strip(),
            'auto_run': bool(self.vars['auto_run'].get()),
            'yooasset': {
                'collector_setting': self.vars['yooasset.collector_setting'].get().strip(),
                'strict': bool(self.vars['yooasset.strict'].get()),
            }
        }
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
            CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass
        self._running = True
        self.btn_run.config(state='disabled')
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
                    code = 0
                finally:
                    sys.stdout, sys.stderr = old_stdout, old_stderr
            except SystemExit as se:
                code = int(getattr(se, 'code', 1) or 0)
            except Exception as e:
                try:
                    messagebox.showerror('导表失败', str(e))
                except Exception:
                    pass
                code = 1
            finally:
                def done():
                    self._running = False
                    self.btn_run.config(state='normal')
                    try:
                        if code == 0:
                            messagebox.showinfo('完成', '导表成功')
                        else:
                            messagebox.showerror('失败', '导表失败，详见日志')
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
    cfg = None
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            cfg = None
    if not cfg:
        # 尝试从旧的批处理文件填充默认值
        try:
            bat_path = APP_DIR / 'ExcelFolder' / '!【导表】.bat'
            if bat_path.exists():
                text = bat_path.read_text(encoding='gbk', errors='ignore')
                def _extract(key: str) -> str | None:
                    import re
                    m = re.search(rf"^set\s+{key}=([^\r\n]+)", text, flags=re.IGNORECASE | re.MULTILINE)
                    return m.group(1).strip() if m else None
                draft = {
                    'excel_root': _extract('input_folder') or '',
                    'output_project': _extract('output_project_folder') or '',
                    'cs_output': _extract('csfile_output_folder') or '',
                    'enum_output': _extract('enum_output_folder') or '',
                }
                # 仅在有至少一个字段时作为初始值
                if any(draft.values()):
                    cfg = draft
        except Exception:
            pass
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
