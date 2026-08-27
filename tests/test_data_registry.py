"""数据源注册表：加载与健康度（离线）。"""

from __future__ import annotations

from pathlib import Path

from bizatlas.data.registry import _env_ready, load_registry, provider_health_list


def test_load_registry_default_exists():
    data = load_registry(None)
    assert data.get("version") == 1
    assert isinstance(data.get("providers"), list)


def test_load_registry_missing_file(tmp_path):
    data = load_registry(tmp_path / "nope.yaml")
    assert data == {"version": 1, "providers": []}


def test_load_registry_empty_yaml(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("", encoding="utf-8")
    data = load_registry(p)
    assert data == {"version": 1, "providers": []}


def test_env_ready_both():
    ok, msg = _env_ready([])  # 空 env → ok
    assert ok is True and msg == "ok"
    miss_ok, miss_msg = _env_ready(["TIANYANCHA_TOKEN"])
    assert miss_ok is False
    assert "missing env" in miss_msg


def test_provider_health_list():
    items = provider_health_list()
    assert items  # 非空
    ids = {h.id for h in items}
    assert "upload" in ids
    # tianyancha：needs_key 且无 token → ok False
    ty = next(h for h in items if h.id == "tianyancha")
    assert ty.ok is False
    # upload：无 key 且 ready → ok True
    up = next(h for h in items if h.id == "upload")
    assert up.ok is True
