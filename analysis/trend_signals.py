"""
trend_signals.py — 逐季時間序列訊號（用租金判斷房價高低與趨勢）

產出兩張表（供 dashboard #2 走勢、#3 推薦使用）：
  outputs/trend_panel.csv   每 (城市,行政區,房型,季) 的 房價/坪、租金/坪、PRR
  outputs/value_screen.csv  每 (城市,行政區,房型) 的 現價、近一年/近半年房價動能、
                            目前 PRR、自身歷史 PRR 中位、同房型跨區 PRR 中位

核心訊號：
  · PRR 隨時間上升 = 房價漲幅超過租金 → 相對基本面變貴
  · 租金走弱但房價僵固 = 估值僵在高檔 → 易鬆動（下修壓力）
  · 房價動能轉負（量先價行的價格端）= 該區正在降溫

資料沿用 prr_validation 的清理（分房型/排車位/踢非市場交易/IQR）。
用法： python analysis/trend_signals.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from prr_validation import load_sale, load_rent, trim_iqr, PING  # 同目錄

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parents[1] / "analysis" / "outputs"


def skey(s: str) -> int:
    """季別排序鍵：'114S3' -> 1143。"""
    return int(s[:3]) * 10 + int(s[-1])


def _season_median(df: pd.DataFrame, gcols: list[str], min_n: int) -> pd.DataFrame:
    g = df.groupby(gcols + ["season"])["unit_m2"]
    med = g.apply(lambda x: trim_iqr(x).median())
    cnt = g.apply(lambda x: len(trim_iqr(x)))
    out = pd.DataFrame({"med": med, "n": cnt}).reset_index()
    return out[out["n"] >= min_n]


def build_panel() -> pd.DataFrame:
    sale, rent = load_sale(), load_rent()
    price = _season_median(sale, ["city", "鄉鎮市區", "房型"], min_n=10)
    price["price_pp"] = (price["med"] * PING / 10000).round(1)            # 萬/坪
    rent_d = _season_median(rent, ["city", "鄉鎮市區", "房型"], min_n=8)
    rent_d["rent_pp"] = (rent_d["med"] * PING).round(0)                   # 元/坪/月
    rent_c = _season_median(rent, ["city", "房型"], min_n=15)
    rent_c["rent_pp_city"] = (rent_c["med"] * PING).round(0)

    p = price[["city", "鄉鎮市區", "房型", "season", "price_pp"]].merge(
        rent_d[["city", "鄉鎮市區", "房型", "season", "rent_pp"]],
        on=["city", "鄉鎮市區", "房型", "season"], how="left").merge(
        rent_c[["city", "房型", "season", "rent_pp_city"]],
        on=["city", "房型", "season"], how="left")
    p["rent_pp"] = p["rent_pp"].fillna(p["rent_pp_city"])   # 行政區租金太稀疏時退回城市層級
    p["prr"] = (p["price_pp"] * 10000 / (p["rent_pp"] * 12)).round(1)
    p["skey"] = p["season"].map(skey)
    return p.sort_values(["city", "鄉鎮市區", "房型", "skey"]).drop(columns="rent_pp_city")


def build_screen(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (city, dist, htype), g in panel.groupby(["city", "鄉鎮市區", "房型"]):
        g = g.sort_values("skey")
        gp = g.dropna(subset=["price_pp"])
        if len(gp) < 8:           # 季數不足者不納入推薦（避免小樣本雜訊）
            continue
        # 動能以 2 季平滑後計算，降低單季雜訊
        sm = gp["price_pp"].rolling(2).mean()
        now = gp["price_pp"].iloc[-1]
        mom_1y = (sm.iloc[-1] - sm.iloc[-5]) / sm.iloc[-5] * 100
        mom_recent = (sm.iloc[-1] - sm.iloc[-3]) / sm.iloc[-3] * 100
        gpr = g.dropna(subset=["prr"])
        prr_now = gpr["prr"].iloc[-1] if len(gpr) else np.nan
        prr_self = gpr["prr"].median() if len(gpr) else np.nan
        rows.append({
            "city": city, "鄉鎮市區": dist, "房型": htype,
            "現價(萬/坪)": now,
            "近一年漲跌%": round(mom_1y, 1),
            "近半年漲跌%": round(mom_recent, 1),
            "目前PRR": prr_now,
            "自身PRR中位": round(prr_self, 1) if pd.notna(prr_self) else np.nan,
        })
    df = pd.DataFrame(rows)
    df["同房型跨區PRR中位"] = df.groupby("房型")["目前PRR"].transform("median").round(1)
    return df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    panel = build_panel()
    panel.to_csv(OUT / "trend_panel.csv", index=False, encoding="utf-8-sig")
    screen = build_screen(panel)
    screen.to_csv(OUT / "value_screen.csv", index=False, encoding="utf-8-sig")
    print(f"trend_panel {len(panel):,} 列 → outputs/trend_panel.csv")
    print(f"value_screen {len(screen):,} 列 → outputs/value_screen.csv\n")

    # 範例：中和大樓 PRR 走勢
    eg = panel[(panel["鄉鎮市區"] == "中和區") & (panel["房型"] == "大樓")]
    print("【範例】中和區大樓 逐季 房價/租金/PRR：")
    print(eg[["season", "price_pp", "rent_pp", "prr"]].to_string(index=False))

    # 範例：大樓 正在降溫(近半年跌) 且 相對便宜(PRR<跨區中位)
    s = screen[screen["房型"] == "大樓"].copy()
    rec = s[(s["近半年漲跌%"] < 0) & (s["目前PRR"] < s["同房型跨區PRR中位"])]
    print("\n【範例】大樓：降溫中 且 相對便宜（建議優先看）：")
    print(rec.sort_values("近半年漲跌%")[
        ["city", "鄉鎮市區", "現價(萬/坪)", "近半年漲跌%", "目前PRR", "同房型跨區PRR中位"]
    ].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
