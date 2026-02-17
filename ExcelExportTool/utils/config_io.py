import json
import re
import sys
from pathlib import Path
from typing import Any, Optional


def get_app_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def get_config_file(app_dir: Path) -> Path:
    return app_dir / 'sheet_config.json'


def save_config(config_file: Path, cfg: dict[str, Any], silent: bool = False) -> bool:
    try:
        config_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:
        if silent:
            return False
        raise


def load_initial_config(app_dir: Path, config_file: Optional[Path] = None) -> Optional[dict[str, Any]]:
    cfg_file = config_file or get_config_file(app_dir)
    cfg: Optional[dict[str, Any]] = None

    if cfg_file.exists():
        try:
            loaded = json.loads(cfg_file.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            cfg = None

    if cfg:
        return cfg

    try:
        bat_path = app_dir / 'ExcelFolder' / '!【导表】.bat'
        if not bat_path.exists():
            return None
        text = bat_path.read_text(encoding='gbk', errors='ignore')

        def _extract(key: str) -> str | None:
            m = re.search(rf"^set\s+{key}=([^\r\n]+)", text, flags=re.IGNORECASE | re.MULTILINE)
            return m.group(1).strip() if m else None

        draft = {
            'excel_root': _extract('input_folder') or '',
            'output_project': _extract('output_project_folder') or '',
            'cs_output': _extract('csfile_output_folder') or '',
            'enum_output': _extract('enum_output_folder') or '',
        }
        if any(draft.values()):
            return draft
    except Exception:
        return None

    return None
