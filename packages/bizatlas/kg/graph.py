from __future__ import annotations

from typing import Any

from bizatlas.ingest.fixtures import fixtures_root, load_fixture_company


def load_fixture_graph(fixture_id: str) -> dict[str, Any] | None:
    path = fixtures_root() / fixture_id / "graph.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def build_guarantee_graph(company_id: str, fixture_id: str | None = None) -> dict[str, Any]:
    """Return nodes/edges for前端 ECharts graph. Prefer fixture graph.json."""
    if fixture_id:
        g = load_fixture_graph(fixture_id)
        if g:
            return g
        # synthesize from company name + guarantee layers metric
        data = load_fixture_company(fixture_id)
        name = data.get("name") or fixture_id
        layers = 1
        for m in data.get("metrics") or []:
            if m.get("name") == "担保链层级":
                layers = int(m.get("value") or 1)
        return _synthesize(name, layers, dishonest=bool((data.get("events") or {}).get("失信被执行")))

    return {
        "nodes": [{"id": company_id, "name": company_id, "category": "主体"}],
        "edges": [],
        "note": "无图谱数据；上传工商关系或使用含 graph.json 的 fixtures",
    }


def _synthesize(root_name: str, layers: int, *, dishonest: bool) -> dict[str, Any]:
    nodes = [{"id": "n0", "name": root_name, "category": "主体", "risk": "self"}]
    edges = []
    prev = "n0"
    for i in range(1, max(1, layers) + 1):
        nid = f"n{i}"
        label = f"关联担保方{i}"
        risk = "high" if i == layers and dishonest else ("warn" if i >= 3 else "normal")
        nodes.append({"id": nid, "name": label, "category": "担保", "risk": risk})
        edges.append({"source": prev, "target": nid, "rel": "担保"})
        prev = nid
    if dishonest:
        nodes[-1]["name"] = nodes[-1]["name"] + "（被执行）"
    return {
        "nodes": nodes,
        "edges": edges,
        "note": "由担保链层级合成的演示图谱（非工商实扫）",
    }
