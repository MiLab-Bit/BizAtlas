"""担保链违约传染推导单测（P1）。"""
from bizatlas.kg.contagion import compute_contagion, contagion_adjusted_pd


def test_contagion_risky_fixture_has_chain():
    # risky fixture 含 graph.json（担保链含失信主体）
    data = compute_contagion("risky", fixture_id="risky")
    assert 0.0 <= data["contagion_score"] <= 1.0
    assert data["direct_exposure"] >= 0
    assert "note" in data


def test_contagion_adjusted_pd_union():
    # 并集上限封顶 1
    p = contagion_adjusted_pd(0.2, 0.9)
    assert p <= 1.0
    assert p >= 0.2  # 传染只增不减


def test_contagion_absorbs_unknown_company():
    # 无图谱数据也不报错，返回降级 note
    data = compute_contagion("no-such-co")
    assert "nodes" in data and "edges" in data
