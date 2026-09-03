"""为背调工作台播种 4 家「不同类型」真实 A 股上市公司的演示数据。

数据来源（全部为真实公开数据，不编造任何指标）：
  * AkShare 财务分析指标 / 财报摘要（免费、无需积分）
  * AkShare 东方财富三大报表（资产负债表 / 利润表，EM 接口）
  * AkShare 新浪日线（最新收盘价，用于推算市值）

标准风控模型：Altman Z-Score（原始上市制造业 5 变量模型）
  Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
    X1 = (流动资产-流动负债)/总资产        （流动性）
    X2 = 留存收益/总资产                    （累积盈利）
    X3 = EBIT/总资产 = (利润总额+财务费用)/总资产  （盈利）
    X4 = 市值/总负债                        （市场偿付缓冲）
    X5 = 营业收入/总资产                    （资产效率）
  区带：Z>2.99 安全 | 1.81<=Z<=2.99 灰色 | Z<1.81 破产预警
  市值 = 最新收盘价 × 股本(面值1元)；留存收益 = 归母权益 - 股本 - 资本公积
        - 盈余公积 - 专项储备 - 一般风险准备 - 少数股东权益 - 其他权益（会计恒等式反推）

设计原则：
  * 只用真实公开数据；拿不到的指标一律留空，由「数据缺口」机制如实呈现。
  * 幂等：可反复执行，先清理本脚本写入的 company_id 再重建。
  * 可追溯：每条指标 source_json 记录数据源、股票代码与报告期。

4 家企业按风险梯度挑选（主办方可直观对比）：
  贵州茅台 600519   消费/白酒   优质低杠杆
  比亚迪   002594   制造/新能源 高杠杆扩张
  万科A    000002   房地产     亏损承压
  华夏幸福 600340   地产       资不抵债（真实违约案例）
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import uuid
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "bizatlas.sqlite"

TARGETS = [
    {"code": "600519", "id": "co-demo-600519", "name": "贵州茅台",
     "industry": "消费/白酒", "kind": "优质低杠杆",
     "note": "高毛利、低负债、现金流充沛，作为健康对照样本"},
    {"code": "002594", "id": "co-demo-002594", "name": "比亚迪",
     "industry": "制造/新能源", "kind": "高杠杆扩张",
     "note": "负债率偏高但保持盈利，短期偿债指标偏紧（Z 值偏低主要源于高杠杆）"},
    {"code": "000002", "id": "co-demo-000002", "name": "万科A",
     "industry": "房地产", "kind": "承压亏损",
     "note": "行业下行，毛利率与 ROE 走弱，已连续亏损"},
    {"code": "600340", "id": "co-demo-600340", "name": "华夏幸福",
     "industry": "房地产", "kind": "资不抵债",
     "note": "资产负债率破 100%（净资产为负），连续多年亏损，真实违约案例"},
]

# AkShare 财务分析指标字段 -> (BizAtlas 指标名, 换算系数；100 表示百分比/100)
MAP = [
    ("流动比率", "流动比率", 1.0),
    ("速动比率", "速动比率", 1.0),
    ("资产负债率(%)", "资产负债率", 100.0),
    ("净资产收益率(%)", "ROE", 100.0),
    ("销售毛利率(%)", "毛利率", 100.0),
    ("销售净利率(%)", "净利率", 100.0),
    ("存货周转率(次)", "存货周转率", 1.0),
    ("应收账款周转率(次)", "应收账款周转率", 1.0),
]


def is_num(v) -> bool:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


def fnum(v):
    try:
        f = float(v)
        return f if (f == f and abs(f) < 1e30) else None
    except (TypeError, ValueError):
        return None


def fetch_indicator(code: str):
    """主接口：财务分析指标（含流动/速动/负债率/ROE/总资产等）。"""
    import akshare as ak
    df = None
    for year in (2026, 2025, 2024, 2023):
        try:
            d = ak.stock_financial_analysis_indicator(symbol=code, start_year=str(year))
            if d is not None and not d.empty:
                df = d
                break
        except Exception:
            continue
    if df is None or df.empty:
        raise RuntimeError(f"{code}: 未取到财报指标")
    row = df.iloc[-1].to_dict()
    return row, str(row.get("日期"))


def fetch_abstract(code: str) -> dict:
    """摘要接口：毛利率 / 商誉 / 经营现金流与净利润之比。"""
    import akshare as ak
    try:
        a = ak.stock_financial_abstract(symbol=code)
    except Exception:
        return {}
    if a is None or a.empty:
        return {}
    cols = [c for c in a.columns if c not in ("选项", "指标")]
    col = next((c for c in cols if a[c].notna().sum() > 5), None)
    if col is None:
        return {}
    return {"_period": col, **{k: v for k, v in zip(a["指标"].astype(str), a[col])}}


def fetch_reports(code: str):
    """东方财富三大报表最新一期（资产负债表 + 利润表，按共同报告期对齐）。"""
    import akshare as ak
    import pandas as pd
    sym = ("SH" if code.startswith("6") else "SZ") + code
    bs = ak.stock_balance_sheet_by_report_em(symbol=sym)
    ps = ak.stock_profit_sheet_by_report_em(symbol=sym)
    bd = pd.to_datetime(bs["REPORT_DATE"], errors="coerce")
    pd_ = pd.to_datetime(ps["REPORT_DATE"], errors="coerce")
    common = set(bd.dropna().dt.strftime("%Y-%m-%d")) & set(pd_.dropna().dt.strftime("%Y-%m-%d"))
    if not common:
        raise RuntimeError(f"{code}: 资产负债表/利润表无共同报告期")
    d = max(common)
    br = bs[bd.dt.strftime("%Y-%m-%d") == d].iloc[0]
    pr = ps[pd_.dt.strftime("%Y-%m-%d") == d].iloc[0]
    return br, pr, str(d)


def latest_price_sina(code: str):
    """新浪日线最新收盘价（用于推算市值）。"""
    import akshare as ak
    sym = ("sh" if code.startswith("6") else "sz") + code
    df = ak.stock_zh_a_daily(symbol=sym, adjust="")
    return float(df.iloc[-1]["close"]), str(df.iloc[-1]["date"])


def compute_altman(br, pr, price, sc) -> dict:
    """计算原始 Altman Z-Score 与分量（真实公开数据）。"""
    TA = fnum(br["TOTAL_ASSETS"])
    CA = fnum(br["TOTAL_CURRENT_ASSETS"])
    CL = fnum(br["TOTAL_CURRENT_LIAB"])
    TE = fnum(br["TOTAL_EQUITY"])
    TL = fnum(br["TOTAL_LIABILITIES"])
    PE = fnum(br["TOTAL_PARENT_EQUITY"])
    SCv = fnum(br["SHARE_CAPITAL"])
    CR = fnum(br["CAPITAL_RESERVE"])
    SR = fnum(br["SURPLUS_RESERVE"])
    SPR = fnum(br.get("SPECIAL_RESERVE")) if "SPECIAL_RESERVE" in br else 0
    GRR = fnum(br.get("GENERAL_RISK_RESERVE")) if "GENERAL_RISK_RESERVE" in br else 0
    ME = fnum(br.get("MINORITY_EQUITY")) if "MINORITY_EQUITY" in br else 0
    EO = fnum(br.get("EQUITY_OTHER")) if "EQUITY_OTHER" in br else 0
    sales = fnum(pr["OPERATE_INCOME"])
    tp = fnum(pr["TOTAL_PROFIT"])
    fe = fnum(pr["FINANCE_EXPENSE"])

    # 留存收益（会计恒等式反推）：归母权益 - 投入资本类科目
    RE = (PE or 0) - (SCv or 0) - (CR or 0) - (SR or 0) - (SPR or 0) - (GRR or 0) - (ME or 0) - (EO or 0)
    mcap = price * (SCv or 0)  # 股本(元)/面值1 = 股数

    X1 = (CA - CL) / TA if (TA and CA is not None and CL is not None) else None
    X2 = RE / TA if (TA and RE is not None) else None
    X3 = (tp + fe) / TA if (TA and tp is not None and fe is not None) else None
    X4 = mcap / TL if (TL and mcap is not None) else None
    X5 = sales / TA if (TA and sales is not None) else None
    comps = [c for c in (X1, X2, X3, X4, X5) if c is not None]
    Z = (1.2 * (X1 or 0) + 1.4 * (X2 or 0) + 3.3 * (X3 or 0)
         + 0.6 * (X4 or 0) + 1.0 * (X5 or 0)) if len(comps) == 5 else None
    return {"Z": Z, "X1": X1, "X2": X2, "X3": X3, "X4": X4, "X5": X5,
            "retained_earnings": RE, "market_cap": mcap, "total_assets": TA,
            "total_liabilities": TL}


def consecutive_loss_years(code: str):
    """按年报口径（12-31）的净利率，从最近一年往前数连续亏损年数。"""
    import akshare as ak
    import pandas as pd
    df = None
    for year in (2023, 2024, 2025, 2026):
        try:
            d = ak.stock_financial_analysis_indicator(symbol=code, start_year=str(year))
            if d is not None and not d.empty:
                df = d if df is None else pd.concat([df, d])
        except Exception:
            continue
    if df is None or df.empty:
        return None
    try:
        df = df.drop_duplicates(subset=["日期"]).sort_values("日期")
    except Exception:
        return None
    annual = []
    for _, r in df.iterrows():
        dd = str(r.get("日期"))
        if dd.endswith("12-31"):
            v = r.get("销售净利率(%)")
            if is_num(v):
                annual.append(float(v))
    if not annual:
        return None
    n = 0
    for v in reversed(annual):
        if v < 0:
            n += 1
        else:
            break
    return n


def build_metrics(row, ab, total_assets):
    """标准比率指标（真实公开数据）；拿不到的留空。"""
    out, skipped = [], []
    for ak_key, ba_name, divisor in MAP:
        raw = row.get(ak_key)
        if not is_num(raw):
            skipped.append(ak_key)
            continue
        out.append((ba_name, round(float(raw) / divisor, 6), "ratio"))
    gm = ab.get("毛利率")
    if is_num(gm):
        out.append(("毛利率", round(float(gm) / 100.0, 6), "ratio"))
    else:
        skipped.append("毛利率")
    gw = ab.get("商誉")
    if is_num(gw) and is_num(total_assets) and float(total_assets) > 0:
        out.append(("商誉占比", round(float(gw) / float(total_assets), 6), "ratio"))
    else:
        skipped.append("商誉占比")
    cfo = ab.get("经营活动净现金/归属母公司的净利润")
    if is_num(cfo):
        out.append(("经营现金流/净利润", round(float(cfo), 6), "ratio"))
    else:
        skipped.append("经营现金流/净利润")
    ic = row.get("利息支付倍数")
    if is_num(ic) and float(ic) > 0:
        out.append(("利息保障倍数", round(float(ic), 6), "ratio"))
    else:
        skipped.append("利息保障倍数(负值/缺失)")
    return out, skipped


def _insert_metric(cur, cid, name, val, unit, as_of, src):
    cur.execute(
        "INSERT INTO financial_metrics "
        "(id, company_id, name, value, unit, tier, as_of, source_json, evidence_refs) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (f"m-{uuid.uuid4().hex[:12]}", cid, name, val, unit, "L2", as_of, src, "[]"),
    )


def main() -> int:
    import akshare as ak  # noqa: F401  (确保可用)
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    ids = [t["id"] for t in TARGETS]
    ph = ",".join("?" * len(ids))
    cur.execute(f"DELETE FROM financial_metrics WHERE company_id IN ({ph})", ids)
    cur.execute(f"DELETE FROM risk_scores WHERE company_id IN ({ph})", ids)
    cur.execute(f"DELETE FROM reports WHERE company_id IN ({ph})", ids)
    cur.execute(f"DELETE FROM companies WHERE id IN ({ph})", ids)
    conn.commit()

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    ok = 0
    for t in TARGETS:
        try:
            row, period = fetch_indicator(t["code"])
        except Exception as e:
            print(f"  [FAIL] {t['name']}({t['code']}): 指标取数失败 {e}")
            continue
        try:
            br, pr, rep_date = fetch_reports(t["code"])
            price, _ = latest_price_sina(t["code"])
            alt = compute_altman(br, pr, price, None)
        except Exception as e:
            print(f"  [WARN] {t['name']}({t['code']}): Z 值取数失败 {e}（仍落库标准比率）")
            alt = None
            rep_date = period

        metrics, skipped = build_metrics(row, fetch_abstract(t["code"]), row.get("总资产(元)"))

        # 连续亏损年数
        try:
            cl = consecutive_loss_years(t["code"])
            if cl:
                metrics.append(("连续亏损年数", float(cl), "count"))
            else:
                skipped.append(f"连续亏损年数({cl})")
        except Exception:
            skipped.append("连续亏损年数(取数失败)")

        # Altman Z 值（标准银行风控模型）
        if alt and alt["Z"] is not None:
            metrics.append(("Altman_Z值", round(alt["Z"], 4), "zscore"))
            skipped.append(f"Altman_Z值={alt['Z']:.3f}")

        src = json.dumps({"type": "api", "ref": f"akshare:{t['code']}", "period": rep_date},
                         ensure_ascii=False)

        cur.execute(
            "INSERT INTO companies (id, name, industry, created_at) VALUES (?,?,?,?)",
            (t["id"], t["name"], t["industry"], now),
        )
        for name, val, unit in metrics:
            _insert_metric(cur, t["id"], name, val, unit, rep_date, src)
        conn.commit()
        ok += 1

        print(f"\n  {t['name']}({t['code']}) · {t['industry']} · 报告期 {rep_date}")
        print(f"    标准比率 {len([m for m in metrics if m[0]!='Altman_Z值'])} 项"
              + (f" | Altman Z = {alt['Z']:.3f}" if alt and alt['Z'] is not None else " | Altman Z 未计算"))
        if alt and alt["Z"] is not None:
            zone = "安全区" if alt["Z"] > 2.99 else ("灰色区" if alt["Z"] >= 1.81 else "破产区")
            print(f"    X1={alt['X1']:.3f} X2={alt['X2']:.3f} X3={alt['X3']:.3f} "
                  f"X4={alt['X4']:.3f} X5={alt['X5']:.3f} → {zone}")
        if skipped:
            print(f"    跳过/备注: {', '.join(skipped)}")

    cur.execute("SELECT COUNT(*) FROM companies")
    total = cur.fetchone()[0]
    conn.close()
    print(f"\n完成: {ok}/{len(TARGETS)} 家落库，companies 总计 {total} 家")
    return 0 if ok == len(TARGETS) else 1


if __name__ == "__main__":
    sys.exit(main())
