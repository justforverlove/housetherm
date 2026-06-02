"""
lvr_gov.py — 內政部實價登錄「不動產成交案件」開放資料下載器（雙北）

資料來源：政府開放資料，合法可重新利用。
  批次季度下載端點： https://plvr.land.moi.gov.tw/DownloadSeason
  每季 zip 含全台各縣市 CSV；本腳本只取雙北的「買賣(a)」與「租賃(c)」主檔。

縣市代碼： a=台北市, f=新北市
檔案類型： *_lvr_land_a.csv = 不動產買賣(成屋), *_lvr_land_c.csv = 不動產租賃
          (預售屋 b 不取；_build/_land/_park 為明細子檔，本分析用主檔即可)

輸出：
  data/raw/zips/<season>.zip        下載快取（避免重複下載）
  data/raw/twin_cities_sale.csv     雙北買賣（多季合併）
  data/raw/twin_cities_rent.csv     雙北租賃（多季合併）

用法：
  python ingestion/scrapers/lvr_gov.py                 # 預設季別
  python ingestion/scrapers/lvr_gov.py 112S1 112S2 ...  # 指定季別
"""
from __future__ import annotations

import io
import sys
import time
import zipfile
import warnings
from pathlib import Path

import requests
import pandas as pd

warnings.filterwarnings("ignore")  # urllib3 LibreSSL warning on macOS system python

ENDPOINT = "https://plvr.land.moi.gov.tw/DownloadSeason"
CITY_CODE = {"a": "台北市", "f": "新北市"}  # 雙北
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
ZIP_CACHE = RAW / "zips"

# 預設抓近年季別（民國年 S 季）。實價登錄有登記時間差，太新的季別可能尚未釋出。
DEFAULT_SEASONS = [f"{y}S{q}" for y in range(111, 116) for q in range(1, 5)]  # 111S1..115S4（未釋出季別自動略過）

# 各主檔保留的欄位（精簡檔案、聚焦 PRR 分析）
SALE_COLS = ["鄉鎮市區", "交易標的", "土地位置建物門牌", "主要用途", "建物型態", "交易年月日",
             "總價元", "單價元平方公尺", "建物移轉總面積平方公尺",
             "車位類別", "車位總價元", "車位移轉總面積平方公尺",
             "建物現況格局-房", "建築完成年月", "備註"]
RENT_COLS = ["鄉鎮市區", "交易標的", "主要用途", "建物型態", "租賃年月日",
             "總額元", "單價元平方公尺", "建物總面積平方公尺", "出租型態"]


def download_season(season: str) -> bytes | None:
    """下載單一季別 zip（有快取就用快取）。回傳 zip bytes，失敗回 None。"""
    ZIP_CACHE.mkdir(parents=True, exist_ok=True)
    cached = ZIP_CACHE / f"{season}.zip"
    if cached.exists() and cached.stat().st_size > 1000:
        return cached.read_bytes()
    try:
        r = requests.get(ENDPOINT,
                         params={"season": season, "type": "zip", "fileName": "lvr_landcsv.zip"},
                         timeout=120, verify=False)
    except Exception as e:
        print(f"  [{season}] 下載錯誤: {e!r}")
        return None
    if not r.ok or r.content[:2] != b"PK":
        print(f"  [{season}] 無有效資料 (status={r.status_code})")
        return None
    cached.write_bytes(r.content)
    print(f"  [{season}] 下載 {len(r.content)//1024} KB")
    return r.content


def extract_city(zbytes: bytes, code: str, kind: str, season: str, cols: list[str]) -> pd.DataFrame:
    """從 zip 取出某縣市某類型主檔，清掉英文表頭列，加上 city/season 標籤。"""
    fname = f"{code}_lvr_land_{kind}.csv"
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    if fname not in z.namelist():
        return pd.DataFrame()
    df = pd.read_csv(z.open(fname), dtype=str)
    df = df.iloc[1:]  # 第一列是英文欄名，丟棄
    df = df[[c for c in cols if c in df.columns]].copy()
    df["city"] = CITY_CODE[code]
    df["season"] = season
    return df


def main(seasons: list[str]):
    RAW.mkdir(parents=True, exist_ok=True)
    sale_parts, rent_parts = [], []
    print(f"下載雙北實價登錄，共 {len(seasons)} 季：")
    for s in seasons:
        zb = download_season(s)
        if zb is None:
            continue
        for code in CITY_CODE:
            sale_parts.append(extract_city(zb, code, "a", s, SALE_COLS))
            rent_parts.append(extract_city(zb, code, "c", s, RENT_COLS))
        time.sleep(0.5)  # 禮貌限速

    sale = pd.concat([d for d in sale_parts if not d.empty], ignore_index=True)
    rent = pd.concat([d for d in rent_parts if not d.empty], ignore_index=True)
    sale.to_csv(RAW / "twin_cities_sale.csv", index=False)
    rent.to_csv(RAW / "twin_cities_rent.csv", index=False)
    print(f"\n完成： 買賣 {len(sale):,} 筆 → data/raw/twin_cities_sale.csv")
    print(f"      租賃 {len(rent):,} 筆 → data/raw/twin_cities_rent.csv")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args if args else DEFAULT_SEASONS)
