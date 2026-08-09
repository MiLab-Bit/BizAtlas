"""KG 担保图谱：加载 / 合成 / build（离线，依赖 fixtures）。"""

from __future__ import annotations

from bizatlas.kg import graph as G


def test_load_fixture_graph_present():
    g = G.load_fixture_graph("risky")
    assert g is not None
    assert "nodes" in g and "edges" in g


def test_load_fixture_graph_missing():
    assert G.load_fixture_graph("does_not_exist_fixture") is None


def test_build_with_fixture_id():
    g = G.build_guarantee_graph("company-x", fixture_id="healthy")
    assert g is not None
    assert "nodes" in g


def test_build_without_fixture_id():
    g = G.build_guarantee_graph("company-x")
    assert g["nodes"][0]["id"] == "company-x"
    assert g["edges"] == []


def test_synthesize_dishonest():
    g = G._synthesize("主体A", 3, dishonest=True)
    assert any("被执行" in n["name"] for n in g["nodes"])
    assert g["nodes"][-1]["risk"] == "high"
    assert g["note"].startswith("由担保链层级")


def test_synthesize_clean():
    g = G._synthesize("主体B", 2, dishonest=False)
    assert not any("被执行" in n["name"] for n in g["nodes"])


def test_build_synthesize_from_fixture(monkeypatch):
    # graph.json 缺失时落到 load_fixture_company + _synthesize 分支
    monkeypatch.setattr(G, "load_fixture_graph", lambda fid: None)
    monkeypatch.setattr(
        G,
        "load_fixture_company",
        lambda fid: {
            "name": "Z Corp",
            "metrics": [{"name": "担保链层级", "value": 3}],
            "events": {"失信被执行": True},
        },
    )
    g = G.build_guarantee_graph("x", fixture_id="synthetic")
    assert g["note"].startswith("由担保链层级")
    assert any("被执行" in n["name"] for n in g["nodes"])
