"""资源校验器测试。"""

import json
from pathlib import Path

from ExcelExportTool.validation.asset_validator import AssetValidator
import ExcelExportTool.validation.asset_validator as asset_validator


def _write_collector(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "- CollectPath: Assets/Game/UI\n- CollectPath: Assets/Game/Prefabs\n",
        encoding="utf-8",
    )


def test_asset_validator_parse_and_exists(tmp_path):
    project = tmp_path
    (project / "Assets" / "Game" / "UI").mkdir(parents=True)
    (project / "Assets" / "Game" / "Prefabs").mkdir(parents=True)
    (project / "Assets" / "Game" / "UI" / "Icon.png").write_text("x", encoding="utf-8")
    (project / "Assets" / "Game" / "Prefabs" / "Hero.prefab").write_text("x", encoding="utf-8")

    collector = project / "Assets" / "YooAsset" / "Collector.asset"
    _write_collector(collector)

    v = AssetValidator(str(collector), strict=True)
    assert "Assets/Game/UI" in v.roots
    assert v.exists_base_name("Icon", "png")
    assert v.exists_base_name("Hero", "prefab")
    assert not v.exists_base_name("Icon", "jpg")


def test_get_asset_validator_cache_and_rebuild(monkeypatch, tmp_path):
    project = tmp_path
    (project / "Assets" / "Game" / "UI").mkdir(parents=True)
    (project / "Assets" / "Game" / "UI" / "Icon.png").write_text("x", encoding="utf-8")
    collector = project / "Assets" / "YooAsset" / "Collector.asset"
    _write_collector(collector)

    cfg = {"yooasset": {"collector_setting": str(collector), "strict": True}}
    monkeypatch.setenv("SHEETEASE_CONFIG_JSON", json.dumps(cfg, ensure_ascii=False))

    asset_validator._ASSET_VALIDATOR = None
    asset_validator._ASSET_VALIDATOR_KEY = None

    v1 = asset_validator.get_asset_validator()
    v2 = asset_validator.get_asset_validator()
    assert v1 is not None
    assert v1 is v2

    cfg2 = {"yooasset": {"collector_setting": str(collector), "strict": False}}
    monkeypatch.setenv("SHEETEASE_CONFIG_JSON", json.dumps(cfg2, ensure_ascii=False))
    v3 = asset_validator.get_asset_validator()
    assert v3 is not None
    assert v3 is not v1
