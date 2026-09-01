"""BizAtlas 风险评分回溯验证 v3（真实引擎 + 真实 A 股历史财务）。
正样本：名称含 ST/*ST 的 A 股（已发生信用风险事件）；负样本：配对非 ST 股。
对每个样本回溯历年年报财务指标，喂入 BizAtlas 真实 RuleEngine + score_risk，
逐条写入 backtest_progress.jsonl（断点续跑），供本地计算 AUC/KS/提前预警期。

特性：
- tushare stock_basic 限流自动退避重试
- akshare stock_financial_abstract（同花顺源，含核心财务）按年映射规则库指标
- ST 起始年 best-effort 采集（用于提前预警期），失败不影响主流程
- 进度落 jsonl，断点续跑（重跑自动跳过已完成的 symbol）
"""
import os, sys, json, time, random, warnings
warnings.filterwarnings("ignore")
ROOT = "/opt/bizatlas"
os.chdir(ROOT)
for p in (ROOT, os.path.join(ROOT, "packages")):
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd
import akshare as ak
import tushare as ts
import dotenv
from bizatlas.risk.score import score_risk
from bizatlas.rules.engine import RuleEngine
from bizatlas.contracts.models import MetricValue, DataTier

PROGRESS = os.path.join(ROOT, "backtest_progress_v4.jsonl")

def ak_retry(func, *a, retries=6, wait=3.0, **kw):
    last = None
    for i in range(retries):
        try:
            return func(*a, **kw)
        except Exception as e:
            last = e
            time.sleep(wait + i)
    raise last

# 规则库指标名 -> (abstract 指标名)
# 注意：abstract 已含 资产负债率/流动比率/速动比率/ROE/毛利率/营收增速/经营现金比。
# 利息保障倍数、产能利用率、集中度、担保类指标在抽象财务中无对应列，缺则显式不喂（引擎按缺失处理）。
MAP = {
    "资产负债率": ("col", "资产负债率"),
    "流动比率": ("col", "流动比率"),
    "速动比率": ("col", "速动比率"),
    "ROE": ("col", "净资产收益率(ROE)"),
    "毛利率": ("col", "毛利率"),
    "行业营收增速": ("col", "营业总收入增长率"),
    "经营现金流/净利润": ("col", "经营活动净现金/归属母公司的净利润"),
}

def ts_to_ak(ts_code: str) -> str:
    code, ex = ts_code.split(".")
    return ex + code

def fetch_abstract_metrics(symbol: str):
    ab = ak_retry(ak.stock_financial_abstract, symbol=symbol)
    if ab is None or ab.empty or "指标" not in ab.columns:
        return []
    period_cols = [c for c in ab.columns if c not in ("选项", "指标")]
    period_cols = [c for c in period_cols if isinstance(c, str) and c.endswith("1231")]
    m = ab.set_index("指标")
    out = []
    for col in period_cols:
        year = int(col[:4])
        if year < 2014:
            continue
        def getv(ind):
            try:
                v = m.loc[ind, col]
                if isinstance(v, pd.Series):
                    v = v.iloc[0]
                return float(v) if pd.notna(v) else None
            except Exception:
                return None
        vals = {}
        for biz, spec in MAP.items():
            if spec[0] == "col":
                v = getv(spec[1])
            else:
                num, den = getv(spec[1]), getv(spec[2])
                v = (num / den) if (num is not None and den not in (None, 0)) else None
            vals[biz] = v
        mvs = [MetricValue(name=b, value=v, tier=DataTier.L1, confidence=1.0)
               for b, v in vals.items() if v is not None]
        if len(mvs) >= 3:
            out.append((year, mvs))
    return out

onset_cache = {}
def get_onset(ak_code):
    if ak_code in onset_cache:
        return onset_cache[ak_code]
    try:
        df = ak_retry(ak.stock_info_change_name, symbol=ak_code)
        if df is not None and not df.empty and "name" in df.columns and "date" in df.columns:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            st_rows = df[df["name"].astype(str).str.contains("ST", case=False, na=False)]
            if not st_rows.empty:
                yr = st_rows["date"].min().year
                onset_cache[ak_code] = yr
                return yr
    except Exception:
        pass
    onset_cache[ak_code] = None
    return None

engine = RuleEngine()

def to_ak(code: str) -> str:
    code = str(code).strip()
    return ("SH" + code) if code.startswith("6") else ("SZ" + code)

def main():
    n_st = int(os.getenv("N_ST", "0")) or None
    n_neg = int(os.getenv("N_NEG", "0")) or None
    dotenv.load_dotenv()
    print("拉取股票列表(akshare 沪深)...", flush=True)
    sh_list = ak_retry(ak.stock_info_sh_name_code)
    sz_list = ak_retry(ak.stock_info_sz_name_code)
    allp = pd.concat([sh_list, sz_list], ignore_index=True)
    allp["code"] = allp["证券代码"].astype(str).str.strip()
    allp["ak"] = allp["code"].map(to_ak)
    allp["is_st_name"] = allp["证券简称"].astype(str).str.contains("ST", case=False, na=False)
    st_codes = allp[allp["is_st_name"]]["ak"].tolist()
    nonst_codes = allp[~allp["is_st_name"]]["ak"].tolist()
    random.seed(42)
    neg_codes = random.sample(nonst_codes, min(len(st_codes), len(nonst_codes)))
    print(f"ST={len(st_codes)} 负样本池={len(neg_codes)}", flush=True)

    # 断点续跑：已完成 symbol 跳过
    done = set()
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["symbol"])
                except Exception:
                    pass
    print(f"已完成 symbol 数={len(done)}（将跳过）", flush=True)

    def run_group(codes, label, cap):
        codes = codes[:cap] if cap else codes
        cnt = 0
        for tc in codes:
            sym = tc
            if sym in done:
                continue
            try:
                rows = fetch_abstract_metrics(sym)
            except Exception:
                time.sleep(0.3); continue
            onset = get_onset(sym) if label == 1 else None
            for year, mvs in rows:
                try:
                    hits = engine.match(mvs, events={})
                    res = score_risk(sym, mvs, hits, events={}, conflicts=0)
                except Exception:
                    continue
                rec = {
                    "symbol": sym, "year": year, "score": round(res.score, 2),
                    "grade": res.grade.value, "is_st": label, "n_metrics": len(mvs),
                    "onset_year": onset,
                }
                if onset is not None:
                    rec["years_to_onset"] = onset - year
                with open(PROGRESS, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt += 1
            if cnt % 10 == 0:
                print(f"[{ 'ST' if label else 'NEG' }] 已处理 {cnt} 只 -> {sym}", flush=True)
            time.sleep(0.1)

    print("正样本评分...", flush=True)
    run_group(st_codes, 1, n_st)
    print("负样本评分...", flush=True)
    run_group(neg_codes, 0, n_neg)
    # 汇总
    recs = [json.loads(l) for l in open(PROGRESS, encoding="utf-8") if l.strip()]
    st_r = [r for r in recs if r["is_st"] == 1]
    neg_r = [r for r in recs if r["is_st"] == 0]
    print(f"DONE total_records={len(recs)} (ST={len(st_r)} NEG={len(neg_r)})", flush=True)
    if st_r: print("ST mean=%.2f" % (sum(r["score"] for r in st_r)/len(st_r)), flush=True)
    if neg_r: print("NEG mean=%.2f" % (sum(r["score"] for r in neg_r)/len(neg_r)), flush=True)

if __name__ == "__main__":
    main()
