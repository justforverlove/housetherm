"""
prr_validation.py — 需求驗證：用實價登錄計算雙北「房價租金比 (PRR)」

核心論點驗證：
  1. 雙北 PRR 偏高 / 租金收益率偏低 → 「房價相對租金基本面偏貴」是真的。
  2. 房價隨時間走勢 → 能判斷「現在比過去高還低」。

PRR = 買賣單價(元/m²) / (租賃月單價(元/m²) × 12)     ← 坪數換算約掉
租金收益率 = 1 / PRR

資料：data/raw/twin_cities_sale.csv, twin_cities_rent.csv（由 lvr_gov.py 產生）
輸出：analysis/outputs/ 下的彙整表 (CSV) 與圖 (PNG)

用法： python analysis/prr_validation.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "analysis" / "outputs"
PING = 3.305785  # 1 坪 = 3.305785 m²

# 建物型態 → 房型（只保留可比的住宅類；套房雙北幾乎無登記、店面/其他排除）
TYPE_MAP = {
    "住宅大樓(11層含以上有電梯)": "大樓",
    "華廈(10層含以下有電梯)": "華廈",
    "公寓(5樓含以下無電梯)": "公寓",
    "透天厝": "透天",
}
# 非市場/特殊交易關鍵字（備註命中即排除，這些成交價偏離市場行情）
EXCLUDE_NOTE = ["親友", "特殊關係", "關係人", "債務", "債權", "拍賣", "破產"]


def to_num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def trim_iqr(s: pd.Series, k=1.5) -> pd.Series:
    """IQR 法去極端值：保留 [Q1−k·IQR, Q3+k·IQR]，比固定百分位更貼合分布。"""
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    return s[(s >= q1 - k * iqr) & (s <= q3 + k * iqr)]


def load_sale() -> pd.DataFrame:
    df = pd.read_csv(RAW / "twin_cities_sale.csv", dtype=str)
    df = df[df["交易標的"].str.startswith("房地", na=False)]
    df = df[df["主要用途"] == "住家用"]
    df["房型"] = df["建物型態"].map(TYPE_MAP)
    df = df[df["房型"].notna()]
    # 純房屋單價（排除車位）： (總價−車位總價) / (建物面積−車位面積)
    house_area = to_num(df["建物移轉總面積平方公尺"]) - to_num(df["車位移轉總面積平方公尺"])
    df["unit_m2"] = (to_num(df["總價元"]) - to_num(df["車位總價元"])) / house_area.where(house_area > 5)
    df = df[df["unit_m2"] > 0]
    # 踢掉非市場交易（親友/特殊關係/債務/拍賣…）
    df = df[~df["備註"].fillna("").str.contains("|".join(EXCLUDE_NOTE))]
    return df


def load_rent() -> pd.DataFrame:
    df = pd.read_csv(RAW / "twin_cities_rent.csv", dtype=str)
    df["unit_m2"] = pd.to_numeric(df["單價元平方公尺"], errors="coerce")
    df = df[df["主要用途"] == "住家用"]
    df = df[df["unit_m2"] > 0]
    df["房型"] = df["建物型態"].map(TYPE_MAP)
    df = df[df["房型"].notna()]
    # 用「整層/整棟」租賃對應「買整戶」，避免分租套房/雅房的每 m² 單價灌水
    df = df[df["出租型態"].str.contains("整", na=False)]
    return df


def prr_by(group_cols, sale: pd.DataFrame, rent: pd.DataFrame) -> pd.DataFrame:
    """依一或多個欄位分組計算 PRR。group_cols 可為字串或字串 list。"""
    if isinstance(group_cols, str):
        group_cols = [group_cols]
    keys = sorted(set(map(tuple, sale[group_cols].itertuples(index=False, name=None)))
                  | set(map(tuple, rent[group_cols].itertuples(index=False, name=None))))
    rows = []
    for key in keys:
        s = trim_iqr(sale.loc[(sale[group_cols] == list(key)).all(axis=1), "unit_m2"])
        r = trim_iqr(rent.loc[(rent[group_cols] == list(key)).all(axis=1), "unit_m2"])
        if len(s) < 30 or len(r) < 15:   # 樣本太少跳過（租賃較稀疏，門檻放寬）
            continue
        sale_m2, rent_m2 = s.median(), r.median()
        prr = sale_m2 / (rent_m2 * 12)
        row = dict(zip(group_cols, key))
        row.update({
            "買賣中位(萬/坪)": round(sale_m2 * PING / 10000, 1),
            "月租中位(元/坪)": round(rent_m2 * PING, 0),
            "PRR(年)": round(prr, 1),
            "租金收益率%": round(100 / prr, 2),
            "n_sale": len(s), "n_rent": len(r),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sale, rent = load_sale(), load_rent()
    print(f"清理後樣本： 買賣 {len(sale):,} 筆 / 租賃(整層) {len(rent):,} 筆\n")

    # ---- 1. 城市 × 房型 PRR ----
    city = prr_by(["city", "房型"], sale, rent)
    print("=" * 64)
    print("【城市 × 房型】雙北房價租金比 (2022–2025 合併)")
    print("=" * 64)
    print(city.to_string(index=False))
    city.to_csv(OUT / "prr_by_city.csv", index=False, encoding="utf-8-sig")

    # ---- 2. 行政區 × 房型 PRR ----
    dist = prr_by(["city", "鄉鎮市區", "房型"], sale, rent).sort_values("PRR(年)", ascending=False)
    dist.to_csv(OUT / "prr_by_district.csv", index=False, encoding="utf-8-sig")
    print("\n" + "=" * 64)
    print("【中和區】各房型驗證（你回報的問題）")
    print("=" * 64)
    print(dist[dist["鄉鎮市區"] == "中和區"].to_string(index=False))
    print("\n【行政區×房型】PRR 最高(最貴) Top 8")
    print(dist.head(8).to_string(index=False))

    # ---- 3. 房價歷史走勢（現在 vs 過去）----
    sale["year"] = sale["season"].str[:3].astype(int) + 1911
    sale["q"] = sale["season"].str[-1]
    trend = (sale.assign(ppp=sale["unit_m2"] * PING / 10000)
                 .groupby(["city", "season"])["ppp"]
                 .apply(lambda x: round(trim_iqr(x).median(), 1))
                 .unstack(0))
    trend.to_csv(OUT / "price_trend_by_season.csv", encoding="utf-8-sig")
    print("\n" + "=" * 64)
    print("【房價走勢】各季買賣中位數 (萬元/坪)")
    print("=" * 64)
    print(trend.to_string())

    # 現在(最新季) vs 過去四年的百分位
    print("\n【現在 vs 過去】最新季房價在 2022–2025 區間的位置：")
    for c in trend.columns:
        series = trend[c].dropna()
        latest = series.iloc[-1]
        pct = (series < latest).mean() * 100
        print(f"  {c}: 最新 {latest} 萬/坪，高於過去 {pct:.0f}% 的季別"
              f"（區間 {series.min()}–{series.max()}）")

    # ---- 匯出清理後成交明細（供 dashboard 比價 #5 / 地圖 #3）----
    PROCESSED = ROOT / "data" / "processed"
    PROCESSED.mkdir(parents=True, exist_ok=True)
    house_area = to_num(sale["建物移轉總面積平方公尺"]) - to_num(sale["車位移轉總面積平方公尺"])
    slim = pd.DataFrame({
        "city": sale["city"], "鄉鎮市區": sale["鄉鎮市區"], "房型": sale["房型"],
        "地址": sale["土地位置建物門牌"], "season": sale["season"],
        "每坪價萬": (sale["unit_m2"] * PING / 10000).round(1),
        "總價萬": (to_num(sale["總價元"]) / 10000).round(0),
        "坪數": (house_area / PING).round(1),
    })
    slim.to_csv(PROCESSED / "sale_clean.csv", index=False, encoding="utf-8-sig")
    print(f"\n清理後成交明細 {len(slim):,} 筆 → data/processed/sale_clean.csv")

    # ---- 4. 圖：行政區 PRR bar + 房價走勢 line ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for f in ["Arial Unicode MS", "PingFang TC", "Heiti TC"]:
            try:
                matplotlib.rcParams["font.sans-serif"] = [f]
                matplotlib.rcParams["axes.unicode_minus"] = False
                break
            except Exception:
                pass
        fig, ax = plt.subplots(1, 2, figsize=(14, 6))
        d = dist[dist["房型"] == "大樓"].sort_values("PRR(年)")
        ax[0].barh(d["鄉鎮市區"], d["PRR(年)"], color="#c0392b")
        ax[0].set_title("雙北各區【大樓】房價租金比 PRR（越高越貴）")
        ax[0].set_xlabel("PRR = 房價 / 年租金（年）")
        ax[0].axvline(d["PRR(年)"].median(), color="gray", ls="--", lw=1)
        trend.plot(ax=ax[1], marker="o")
        ax[1].set_title("雙北房價走勢（中位數 萬元/坪）")
        ax[1].set_xlabel("季別"); ax[1].set_ylabel("萬元/坪")
        plt.tight_layout()
        plt.savefig(OUT / "prr_overview.png", dpi=120)
        print(f"\n圖已輸出： {OUT / 'prr_overview.png'}")
    except Exception as e:
        print(f"\n(圖表略過: {e})")

    print(f"\n彙整表輸出於： {OUT}/")


if __name__ == "__main__":
    main()
