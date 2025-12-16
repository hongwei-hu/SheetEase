# Author: huhongwei 306463233@qq.com
# MIT License
"""
资源文件校验模块：处理 [Asset] 和 [Asset:ext] 标记的资源文件校验。
"""
import json
import re
import os
from typing import Any, Dict, List, Optional, Tuple


class _AssetEntry:
    """资源条目数据结构"""
    __slots__ = ("base", "ext", "path", "root")
    
    def __init__(self, base: str, ext: str, path: str, root: str) -> None:
        # base：不含扩展名，保留实际大小写
        # ext：不带点的小写（如 'png','prefab'）
        self.base = base
        self.ext = ext
        self.path = path
        self.root = root


class AssetValidator:
    """资源文件校验器：根据 YooAsset 收集设置验证资源文件是否存在"""
    
    def __init__(self, collector_setting: str, strict: bool = False) -> None:
        self.collector_setting = collector_setting
        self.strict = bool(strict)
        self.project_root = self._infer_project_root(collector_setting)
        self.roots = self._parse_collect_paths(collector_setting)
        self._index: Dict[str, List[_AssetEntry]] = {}
        if self.project_root and self.roots:
            self._build_index()

    def _infer_project_root(self, collector_setting: str) -> str:
        """从收集设置文件路径推断项目根目录"""
        try:
            p = os.path.abspath(collector_setting).replace("\\", "/")
            parts = p.split("/")
            if "Assets" in parts:
                idx = parts.index("Assets")
                root = "/".join(parts[:idx])
                return root if root else "/"
        except Exception:
            pass
        return ""

    def _parse_collect_paths(self, collector_setting: str) -> List[str]:
        """解析收集设置文件中的 CollectPath 路径"""
        paths: List[str] = []
        try:
            with open(collector_setting, "r", encoding="utf-8") as f:
                for line in f:
                    # 匹配形如：  - CollectPath: Assets/...
                    m = re.search(r"CollectPath:\s*(Assets/[^\r\n]+)", line)
                    if m:
                        path = m.group(1).strip()
                        # 统一去除尾部斜杠
                        if path.endswith("/"):
                            path = path[:-1]
                        if path not in paths:
                            paths.append(path)
        except Exception:
            return []
        return paths

    def _build_index(self) -> None:
        """构建资源文件索引"""
        proj = self.project_root
        idx: Dict[str, List[_AssetEntry]] = {}
        for root in self.roots:
            abs_root = os.path.join(proj, root.replace("/", os.sep))
            if not os.path.isdir(abs_root):
                continue
            for dirpath, _dirnames, filenames in os.walk(abs_root):
                for fn in filenames:
                    if fn.endswith(".meta"):
                        continue
                    base, ext = os.path.splitext(fn)
                    ext = (ext[1:].lower() if ext else "")  # 去掉点
                    entry = _AssetEntry(base=base, ext=ext, path=os.path.join(dirpath, fn), root=root)
                    key = base.lower()
                    idx.setdefault(key, []).append(entry)
        self._index = idx

    def exists_base_name(self, base_name: str, required_ext: Optional[str]) -> bool:
        """检查是否存在指定文件名（不含扩展名）的资源文件"""
        if not self._index:
            return False
        key = base_name.lower().strip()
        cand = self._index.get(key, [])
        if not cand:
            return False
        # 文件名严格大小写匹配；扩展名忽略大小写
        if required_ext:
            req = required_ext.strip().lstrip(".").lower()
            return any(e.base == base_name and e.ext == req for e in cand)
        else:
            return any(e.base == base_name for e in cand)


# 资产校验：全局缓存（同一次导表仅解析与索引一次）
_ASSET_VALIDATOR = None  # type: ignore
_ASSET_VALIDATOR_KEY: Optional[Tuple[str, bool]] = None  # (collector_setting_path, strict)


def _load_sheet_config_for_assets() -> Optional[Dict[str, Any]]:
    """按优先级加载配置：
    1) 环境变量 SHEETEASE_CONFIG_JSON（直接提供JSON字符串）
    2) 环境变量 SHEETEASE_CONFIG_PATH（指定配置文件路径）
    3) 候选路径：CWD/sheet_config.json 与 仓库根/sheet_config.json
    """
    # 1) 直接从环境变量读取 JSON 字符串
    try:
        env_json = os.environ.get('SHEETEASE_CONFIG_JSON')
        if env_json:
            return json.loads(env_json)
    except Exception:
        pass
    # 2) 指定路径
    try:
        env_path = os.environ.get('SHEETEASE_CONFIG_PATH')
        if env_path and os.path.isfile(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    # 3) 常规候选
    candidates = []
    try:
        candidates.append(os.path.join(os.getcwd(), "sheet_config.json"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sheet_config.json"))
    except Exception:
        pass
    for p in candidates:
        try:
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            continue
    return None


def get_asset_validator() -> Optional[AssetValidator]:
    """按当前配置返回（并必要时重建）资产校验器。
    若切换了 collector 路径或 strict 选项，会自动丢弃旧缓存并重建，避免 GUI 多次运行时使用旧配置。
    """
    global _ASSET_VALIDATOR, _ASSET_VALIDATOR_KEY
    cfg = _load_sheet_config_for_assets()
    if not cfg:
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None
    yoo = cfg.get("yooasset") or {}
    collector = yoo.get("collector_setting")
    strict = bool(yoo.get("strict", False))
    # 当 collector 不存在时直接返回 None（并清空缓存）
    if not collector or not os.path.isfile(collector):
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None
    key = (os.path.abspath(collector), strict)
    if _ASSET_VALIDATOR is not None and _ASSET_VALIDATOR_KEY == key:
        return _ASSET_VALIDATOR
    # 重建
    try:
        validator = AssetValidator(collector, strict=strict)
        if not validator.roots:
            _ASSET_VALIDATOR = None
            _ASSET_VALIDATOR_KEY = None
            return None
        _ASSET_VALIDATOR = validator
        _ASSET_VALIDATOR_KEY = key
        return _ASSET_VALIDATOR
    except Exception:
        _ASSET_VALIDATOR = None
        _ASSET_VALIDATOR_KEY = None
        return None

