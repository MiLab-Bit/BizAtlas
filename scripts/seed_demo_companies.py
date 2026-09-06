"""为背调工作台播种 4 家真实 A 股上市公司的演示数据（银行风控模型口径）。

数据来源（全部为真实公开数据，不编造任何指标）：
  * AkShare 财务分析指标 / 财报摘要（免费、无需积分）
  * AkShare 东方财富三大报表（资产负债表 / 利润表，EM 接口）

标准风控模型：
  1) Altman Z'-Score（1983 账面价值变体，私有/非上市适用）：
       Z' = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4'
       X1 = (流动资产-流动负债)/总资产
       X2 = 留存收益/总资产
       X3 = (利润总额+财务费用)/总资产
       X4'= 总权益/总负债
     区带（私有公司 Z' 口径）：Z'<1.23 破产区 | 1.23<=Z'<2.9 灰色区 | >=2.9 安全
  2) 利息保障倍数 = (利润总额+财务费用)/财务费用（仅当财务费用>0 时落库）
  3) 连续亏损年数（年报 12-31 口径的销售净利率连续为负）

设计原则：
  * 只用真实公开数据；拿不到的指标一律留空，由「数据缺口」机制如实呈现。
  * 幂等：可反复执行，先清理本脚本写入的 company_id 再重建。
  * 可追溯：每条指标 source_json 记录数据源、股票代码与报告期。
  * 容错：单家失败不影响其他家；AkShare 接口偶发中断重试 3 次。

4 家企业按风险梯度挑选：
  贵州茅台 600519   消费/白酒   优质低杠杆（GREEN）
  比亚迪   002594   制造/新能源 高杠杆扩张（YELLOW）
  万科A    000002   房地产     亏损承压（ORANGE）
  华夏幸福 600340   地产       资不抵债（RED，真实违约案例）
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
     "note": "负债率偏高但保持盈利，短期偿债指标偏紧（Z' 偏低主要源于高杠杆）"},
    {"code": "000002", "id": "co-demo-000002", "name": "万科A",
     "industry": "房地产", "kind": "承压亏损",
     "note": "行业下行，毛利率与 ROE 走弱，已连续亏损"},
    {"code": "600340", "id": "co-demo-600340", "name": "华夏幸福",
     "industry": "房地产", "kind": "资不抵债",
     "note": "资产负债率破 100%（净资产为负），连续多年亏损，真实违约案例"},
]

# 财务分析指标字段 -> (BizAtlas 指标名, 换算系数；100 表示百分比/100)
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


def call_akshare(fn, *args, **kwargs):
    """AkShare 调用：偶发连接中断重试 3 次。"""
    import akshare as ak  # noqa: F401
    last = None
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("akshare call failed")


def fetch_indicator(code: str):
    """主接口：财务分析指标（含流动/速动/负债率/ROE/总资产等）。

    优先 2026，缺失时回退到 2025/2024/2023，取最新一期 iloc[-1]。
    """
    import akshare as ak
    df = None
    used_year = None
    for year in (2026, 2025, 2024, 2023):
        try:
            d = call_akshare(ak.stock_financial_analysis_indicator, symbol=code, start_year=str(year))
            if d is not None and not d.empty:
                df = d
                used_year = year
                break
        except Exception:
            continue
    if df is None or df.empty:
        raise RuntimeError(f"{code}: 未取到财报指标")
    row = df.iloc[-1].to_dict()
    return row, str(row.get("日期")), used_year


def fetch_abstract(code: str) -> dict:
    """摘要接口：毛利率 / 商誉 / 经营现金流与净利润之比。"""
    import akshare as ak
    try:
        a = call_akshare(ak.stock_financial_abstract, symbol=code)
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
    bs = call_akshare(ak.stock_balance_sheet_by_report_em, symbol=sym)
    ps = call_akshare(ak.stock_profit_sheet_by_report_em, symbol=sym)
    bd = pd.to_datetime(bs["REPORT_DATE"], errors="coerce")
    pd_ = pd.to_datetime(ps["REPORT_DATE"], errors="coerce")
    common = set(bd.dropna().dt.strftime("%Y-%m-%d")) & set(pd_.dropna().dt.strftime("%Y-%m-%d"))
    if not common:
        raise RuntimeError(f"{code}: 资产负债表/利润表无共同报告期")
    d = max(common)
    br = bs[bd.dt.strftime("%Y-%m-%d") == d].iloc[0]
    pr = ps[pd_.dt.strftime("%Y-%m-%d") == d].iloc[0]
    return br, pr, str(d)


def compute_zscore_prime(br, pr) -> dict:
    """计算 Altman Z'-Score（1983 账面价值变体）。

    字段（东财英文字段名）：
      X1 = (TOTAL_CURRENT_ASSETS - TOTAL_CURRENT_LIAB) / TOTAL_ASSETS
      X2 = 留存收益 / TOTAL_ASSETS
           留存收益 = TOTAL_PARENT_EQUITY - SHARE_CAPITAL - CAPITAL_RESERVE
                     - SURPLUS_RESERVE - (SPECIAL_RESERVE) - (GENERAL_RISK_RESERVE)
                     - (MINORITY_EQUITY) - (EQUITY_OTHER)
      X3 = (TOTAL_PROFIT + FINANCE_EXPENSE) / TOTAL_ASSETS
      X4'= TOTAL_EQUITY / TOTAL_LIABILITIES
      Z' = 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4'
    """
    TA = fnum(br.get("TOTAL_ASSETS"))
    CA = fnum(br.get("TOTAL_CURRENT_ASSETS"))
    CL = fnum(br.get("TOTAL_CURRENT_LIAB"))
    TE = fnum(br.get("TOTAL_EQUITY"))
    TL = fnum(br.get("TOTAL_LIABILITIES"))
    PE = fnum(br.get("TOTAL_PARENT_EQUITY"))
    SCv = fnum(br.get("SHARE_CAPITAL"))
    CR = fnum(br.get("CAPITAL_RESERVE"))
    SR = fnum(br.get("SURPLUS_RESERVE"))
    SPR = fnum(br.get("SPECIAL_RESERVE")) if "SPECIAL_RESERVE" in br else 0
    GRR = fnum(br.get("GENERAL_RISK_RESERVE")) if "GENERAL_RISK_RESERVE" in br else 0
    ME = fnum(br.get("MINORITY_EQUITY")) if "MINORITY_EQUITY" in br else 0
    EO = fnum(br.get("EQUITY_OTHER")) if "EQUITY_OTHER" in br else 0
    tp = fnum(pr.get("TOTAL_PROFIT"))
    fe = fnum(pr.get("FINANCE_EXPENSE"))

    RE = ((PE or 0) - (SCv or 0) - (CR or 0) - (SR or 0)
          - (SPR or 0) - (GRR or 0) - (ME or 0) - (EO or 0))

    X1 = (CA - CL) / TA if (TA and CA is not None and CL is not None) else None
    X2 = RE / TA if (TA and RE is not None) else None
    X3 = (tp + fe) / TA if (TA and tp is not None and fe is not None) else None
    X4p = TE / TL if (TL and TE is not None) else None

    if None in (X1, X2, X3, X4p):
        Zp = None
    else:
        Zp = 0.717 * X1 + 0.847 * X2 + 3.107 * X3 + 0.420 * X4p
    return {"Z": Zp, "X1": X1, "X2": X2, "X3": X3, "X4p": X4p,
            "retained_earnings": RE, "total_assets": TA,
            "total_liabilities": TL, "finance_expense": fe,
            "total_profit": tp}


def interest_coverage(pr) -> float | None:
    """利息保障倍数 = (利润总额+财务费用)/财务费用；仅当财务费用>0 时落库。

    若财务费用<=0（净利息收入为非负，无偿债负担），返回 None 跳过，
    避免 R1016 误触发。
    """
    tp = fnum(pr.get("TOTAL_PROFIT"))
    fe = fnum(pr.get("FINANCE_EXPENSE"))
    if fe is None or tp is None:
        return None
    if fe <= 0:
        return None
    return (tp + fe) / fe


def consecutive_loss_years(code: str):
    """按年报口径（12-31）的销售净利率，从最近一年往前数连续亏损年数。"""
    import akshare as ak
    import pandas as pd
    df = None
    for year in (2023, 2024, 2025, 2026):
        try:
            d = call_akshare(ak.stock_financial_analysis_indicator, symbol=code, start_year=str(year))
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


def build_metrics(row, ab, total_assets, ic_raw):
    """标准比率指标（真实公开数据）；拿不到的留空。

    ic_raw: 主接口取到的「利息支付倍数」（仅当>0 时落库为 利息支付倍数）。
    """
    out, skipped = [], []
    for ak_key, ba_name, divisor in MAP:
        raw = row.get(ak_key)
        if not is_num(raw):
            skipped.append(ak_key)
            continue
        out.append((ba_name, round(float(raw) / divisor, 6), "ratio"))

    # 毛利率若主接口缺失，从摘要补充
    gm_main = row.get("销售毛利率(%)")
    if not is_num(gm_main):
        gm = ab.get("毛利率")
        if is_num(gm):
            out.append(("毛利率", round(float(gm) / 100.0, 6), "ratio"))
        else:
            skipped.append("毛利率")
    # 主接口已有毛利率时不再重复（已在 MAP 中）

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

    # 利息支付倍数（主接口原始值，仅当>0 时存）
    if is_num(ic_raw) and float(ic_raw) > 0:
        out.append(("利息支付倍数", round(float(ic_raw), 6), "ratio"))
    else:
        skipped.append("利息支付倍数(负值/缺失)")

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
        code = t["code"]
        try:
            row, period, used_year = fetch_indicator(code)
        except Exception as e:
            print(f"  [FAIL] {t['name']}({code}): 指标取数失败 {e}")
            continue

        # 三大报表（Z' 与利息保障倍数依赖）
        alt = None
        ic = None
        rep_date = period
        try:
            br, pr, rep_date = fetch_reports(code)
            alt = compute_zscore_prime(br, pr)
            ic = interest_coverage(pr)
        except Exception as e:
            print(f"  [WARN] {t['name']}({code}): 三大报表取数失败 {e}（仍落库标准比率）")
            alt = None
            ic = None

        ab = fetch_abstract(code)
        total_assets = row.get("总资产(元)")
        metrics, skipped = build_metrics(row, ab, total_assets, row.get("利息支付倍数"))

        # Z'-Score（标准银行风控模型，账面价值变体）
        z_val = None
        if alt and alt["Z"] is not None:
            z_val = round(alt["Z"], 4)
            metrics.append(("Z值(Altman)", z_val, "zscore"))
        else:
            skipped.append("Z值(Altman)(未计算)")

        # 利息保障倍数（仅当财务费用>0）
        if ic is not None:
            metrics.append(("利息保障倍数", round(ic, 6), "ratio"))
        else:
            skipped.append("利息保障倍数(财务费用<=0跳过)")

        # 连续亏损年数
        try:
            cl = consecutive_loss_years(code)
            if cl:
                metrics.append(("连续亏损年数", float(cl), "count"))
            else:
                skipped.append("连续亏损年数(0/无)")
        except Exception as e:
            skipped.append(f"连续亏损年数(取数失败:{e})")

        src = json.dumps({"type": "api", "ref": f"akshare:{code}", "period": rep_date},
                         ensure_ascii=False)

        cur.execute(
            "INSERT INTO companies (id, name, industry, created_at) VALUES (?,?,?,?)",
            (t["id"], t["name"], t["industry"], now),
        )
        for name, val, unit in metrics:
            _insert_metric(cur, t["id"], name, val, unit, rep_date, src)
        conn.commit()
        ok += 1

        print(f"\n  {t['name']}({code}) · {t['industry']} · 指标报告期 {period} · 报表报告期 {rep_date}")
        print(f"    落库指标 {len(metrics)} 项: " + ", ".join(m[0] for m in metrics))
        if z_val is not None:
            zone = "破产区" if z_val < 1.23 else ("灰色区" if z_val < 2.9 else "安全区")
            print(f"    Z值(Altman)={z_val:.4f} ({zone})  "
                  f"X1={alt['X1']:.3f} X2={alt['X2']:.3f} X3={alt['X3']:.3f} X4'={alt['X4p']:.3f}")
        print(f"    利息保障倍数=" + (f"{ic:.3f}" if ic is not None else "跳过(财务费用<=0)"))
        cl = next((m[1] for m in metrics if m[0] == "连续亏损年数"), None)
        print(f"    连续亏损年数=" + (str(cl) if cl is not None else "0/无"))
        if skipped:
            print(f"    跳过/备注: {', '.join(skipped)}")

    cur.execute("SELECT COUNT(*) FROM companies")
    total = cur.fetchone()[0]
    conn.close()
    print(f"\n完成: {ok}/{len(TARGETS)} 家落库，companies 总计 {total} 家")
    return 0 if ok == len(TARGETS) else 1


if __name__ == "__main__":
    sys.exit(main())
