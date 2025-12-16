# Author: huhongwei 306463233@qq.com
# Created: 2024-09-10
# MIT License 
# All rights reserved

from .export_process import batch_excel_to_json
from ..utils.user_utils import user_confirm

import sys
import json
import os
from pathlib import Path


def _contains_assets(*paths) -> bool:
    for p in paths:
        if p and "assets" in str(p).replace("\\", "/").lower():
            return True
    return False


def _is_writable_dir(p: str) -> bool:
    try:
        if not p:
            return False
        os.makedirs(p, exist_ok=True)
        testfile = Path(p) / '.sheetease_write_test.tmp'
        with open(testfile, 'w', encoding='utf-8') as f:
            f.write('ok')
        testfile.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _excel_count(excel_root: str) -> int:
    try:
        p = Path(excel_root)
        if not p.is_dir():
            return 0
        return sum(1 for f in p.rglob('*.xlsx') if f.name and f.name[0].isupper() and not f.name.startswith('~$'))
    except Exception:
        return 0


def _strict_validate(cfg: dict, force_no_assets: bool) -> tuple[bool, str]:
    # 基础路径
    excel_root = cfg.get('excel_root', '')
    output_project = cfg.get('output_project', '')
    cs_output = cfg.get('cs_output', '')
    enum_output = cfg.get('enum_output', '')
    if not excel_root or not Path(excel_root).is_dir():
        return False, f"Excel 根目录不存在: {excel_root}"
    if _excel_count(excel_root) <= 0:
        return False, "表格目录没有任何符合导出规范的表格。命名规则：扩展名 .xlsx，文件名首字母需大写，不以 ~$ 开头"
    for k, v in (('output_project', output_project), ('cs_output', cs_output), ('enum_output', enum_output)):
        if not v:
            return False, f"配置缺少或为空: {k}"
        # 可创建 & 可写
        if not _is_writable_dir(v):
            return False, f"输出目录不可写: {v}"
    # Assets 检查仅警告，不阻止导出
    return True, ''


def _load_config_from_candidates() -> dict | None:
    # 优先当前工作目录，其次包的父目录（仓库根）
    candidates = [Path.cwd() / 'sheet_config.json', Path(__file__).resolve().parents[1] / 'sheet_config.json']
    for c in candidates:
        try:
            if c.exists():
                return json.loads(c.read_text(encoding='utf-8'))
        except Exception:
            continue
    return None


def main():
    argv = sys.argv[1:]
    diff_only = True
    dry_run = False
    force_no_assets = False
    cfg: dict | None = None

    # 支持 --config/-c 使用 json 配置；若未提供 4 个位置参数则尝试加载默认 sheet_config.json
    cfg_path_used: str | None = None
    if '--config' in argv or '-c' in argv:
        try:
            idx = argv.index('--config') if '--config' in argv else argv.index('-c')
            cfg_path = Path(argv[idx + 1]) if len(argv) > idx + 1 else Path('sheet_config.json')
            try:
                cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
                cfg_path_used = str(cfg_path)
            except Exception:
                # 配置不存在或读取失败 -> 启动 GUI 进行配置
                print(f"未找到或无法读取配置: {cfg_path}. 将启动 GUI 进行配置...")
                try:
                    # 在同一进程启动 GUI；用户保存后，app_main 默认写入仓库根 sheet_config.json
                    from .. import app_main as _gui
                    _gui.main()
                except Exception as e:
                    print(f"启动 GUI 失败: {e}")
                    sys.exit(1)
                # GUI 关闭后，尝试从仓库根读取配置并复制到目标路径
                root_cfg = Path(__file__).resolve().parents[1] / 'sheet_config.json'
                if not root_cfg.exists():
                    print("未检测到已保存的配置文件，请在 GUI 中点击“保存配置”后重试。")
                    sys.exit(1)
                try:
                    cfg = json.loads(root_cfg.read_text(encoding='utf-8'))
                    cfg_path_used = str(root_cfg)
                    # 将仓库根配置同步到指定的 cfg_path，方便下次直接使用
                    try:
                        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
                    except Exception:
                        pass
                except Exception as e:
                    print(f"读取 GUI 保存的配置失败: {e}")
                    sys.exit(1)
        except Exception as e:
            print(f"读取配置失败: {e}")
            sys.exit(1)
        # 清理已解析的参数
        if '--config' in argv:
            i = argv.index('--config')
            del argv[i:i+2]
        elif '-c' in argv:
            i = argv.index('-c')
            del argv[i:i+2]
    elif len(argv) < 4:
        cfg = _load_config_from_candidates()
        if not cfg:
            print("用法: python export_all.py <Excel根目录> <工程配置输出> <C#脚本输出> <枚举输出> [--no-diff] [--dry-run] [--force-no-assets] [--config <file>]")
            print("或: python export_all.py --config sheet_config.json")
            sys.exit(1)

    if '--no-diff' in argv:
        diff_only = False
        argv.remove('--no-diff')
    if '--dry-run' in argv:
        dry_run = True
        argv.remove('--dry-run')
    if '--force-no-assets' in argv:
        force_no_assets = True
        argv.remove('--force-no-assets')

    if cfg is None:
        # 兼容旧参数顺序
        root_folder = argv[0]
        output_project_folder = argv[1]
        csfile_output_folder = argv[2]
        enum_output_folder = argv[3]
        cfg = {
            'excel_root': root_folder,
            'output_project': output_project_folder,
            'cs_output': csfile_output_folder,
            'enum_output': enum_output_folder,
        }

    ok, msg = _strict_validate(cfg, force_no_assets=force_no_assets)
    if not ok:
        print(f"配置无效：{msg}")
        sys.exit(1)
    # 将当前配置透传给子流程（供资产校验读取）
    try:
        os.environ['SHEETEASE_CONFIG_JSON'] = json.dumps(cfg, ensure_ascii=False)
        if cfg_path_used:
            os.environ['SHEETEASE_CONFIG_PATH'] = cfg_path_used
    except Exception:
        pass
    # 若输出路径不在 Assets 下 -> 仅警告继续
    if not _contains_assets(cfg.get('output_project',''), cfg.get('cs_output',''), cfg.get('enum_output','')):
        print("[Warn] 输出路径未包含 'Assets'，这通常不是 Unity 工程的 Assets 子目录（将继续导表）")

    batch_excel_to_json(
        cfg['excel_root'],
        output_client_folder=None,
        output_project_folder=cfg['output_project'],
        csfile_output_folder=cfg['cs_output'],
        enum_output_folder=cfg['enum_output'],
        diff_only=diff_only,
        dry_run=dry_run,
        auto_cleanup=True,
    )


if __name__ == '__main__':
    main()