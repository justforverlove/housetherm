"""
房價溫度計 HouseTherm — Streamlit dashboard

功能：
  選城市/行政區/房型 → PRR 溫度 → 現在vs過去 → 評估開價+比價(#5)
  → 新青安試算 → 政策與風險訊號(#4) → 地圖(#3) → 各區比較
  側邊欄「更新資料」按鈕觸發合法的實價登錄 pipeline(#6)

資料：analysis/outputs/（彙整表）、data/processed/sale_clean.csv（成交明細）
執行：streamlit run delivery/dashboard/app.py
"""
import sys
from datetime import date
from pathlib import Path

import matplotlib
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from delivery.calculator.loan import (PRODUCTS, mortgage, monthly_payment,  # noqa: E402
                                       max_loan_from_payment, DEFAULTS)
from delivery.dashboard.districts import DISTRICT_LATLON  # noqa: E402
from ingestion.pipeline import refresh  # noqa: E402

OUT = ROOT / "analysis" / "outputs"
PROCESSED = ROOT / "data" / "processed"
# 中文字型 fallback：Mac 用前三者、Linux/容器用 Noto CJK（見 Dockerfile 安裝 fonts-noto-cjk）
matplotlib.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang TC", "Heiti TC",
                                          "Noto Sans CJK TC", "Noto Sans TC", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False


@st.cache_data
def load():
    dist = pd.read_csv(OUT / "prr_by_district.csv")
    trend = pd.read_csv(OUT / "price_trend_by_season.csv", index_col=0)
    return dist, trend


@st.cache_data
def load_tx():
    return pd.read_csv(PROCESSED / "sale_clean.csv")


@st.cache_data
def load_signals():
    panel = pd.read_csv(OUT / "trend_panel.csv")
    screen = pd.read_csv(OUT / "value_screen.csv")
    return panel, screen


def pct_change(series, n=4):
    s = series.dropna()
    if len(s) > n:
        return (s.iloc[-1] - s.iloc[-1 - n]) / s.iloc[-1 - n] * 100
    return None


def timing_light(prr, type_median, mom_recent):
    """綜合估值(PRR vs 同型中位)與動能(近半年漲跌) → 進場時機燈號。"""
    over = prr > type_median + 2
    cheap = prr < type_median - 2
    cooling = mom_recent is not None and mom_recent < -1
    rising = mom_recent is not None and mom_recent > 1
    if over and rising:
        return "🔴", "估值偏高且仍在上漲 → 追高風險大，建議觀望或嚴格議價。"
    if over and cooling:
        return "🟡", "估值偏高但已降溫 → 可等回穩並積極議價。"
    if cheap and cooling:
        return "🟢", "估值相對便宜且正在降溫 → 相對較佳的進場點，仍應議價。"
    if cheap and rising:
        return "🟡", "估值相對便宜但開始走揚 → 可留意、別追高。"
    if cooling:
        return "🟡", "估值中性、價格降溫中 → 可逢低議價。"
    if rising:
        return "🟡", "估值中性、價格走揚 → 留意追高。"
    return "🟡", "估值與動能均中性 → 依需求、屋況與機能決定。"


def get_mom(city, d, htype):
    r = screen[(screen["city"] == city) & (screen["鄉鎮市區"] == d) & (screen["房型"] == htype)]
    return float(r["近半年漲跌%"].iloc[0]) if len(r) else None


def get_comps(city, d, htype, size, tol, yr_lo, yr_hi):
    """同區同房型、坪數區間 [size±tol]、指定年份區間的成交，近期在前。"""
    c = tx[(tx["city"] == city) & (tx["鄉鎮市區"] == d) & (tx["房型"] == htype)].copy()
    c["yr"] = c["season"].str[:3].astype(int)
    c = c[(c["坪數"] >= size - tol) & (c["坪數"] <= size + tol)
          & (c["yr"] >= yr_lo) & (c["yr"] <= yr_hi)]
    c["skey"] = c["yr"] * 10 + c["season"].str[-1].astype(int)
    return c.sort_values("skey", ascending=False)


def div_hex(v, center, half):
    """紅綠發散色：v>center→紅(偏貴/上漲)，v<center→綠(便宜/降溫)。
    RdYlGn_r(0)=綠、(1)=紅，故高值對應大 t。"""
    t = 0.5 if not half else min(1.0, max(0.0, 0.5 + (v - center) / (2 * half)))
    return mcolors.to_hex(matplotlib.colormaps["RdYlGn_r"](t))


dist, trend = load()
tx = load_tx()
panel, screen = load_signals()

st.set_page_config(page_title="房價溫度計 HouseTherm", page_icon="🌡️", layout="wide")

# ---------- 側邊欄：資料更新 pipeline (#6) ----------
with st.sidebar:
    st.header("📦 資料")
    st.caption(f"季別範圍：{trend.index.min()} – {trend.index.max()}")
    st.caption(f"成交明細：{len(tx):,} 筆（清理後）")
    if st.button("🔄 更新實價登錄資料", use_container_width=True):
        box = st.empty()
        logs = []
        def log(m):
            logs.append(m)
            box.code("\n".join(logs))
        try:
            with st.spinner("pipeline 執行中：ingestion → processing → serving …"):
                refresh(log=log)
            st.cache_data.clear()
            st.success("更新完成，重新載入…")
            st.rerun()
        except Exception as e:
            st.error(f"更新失敗：{e}")
    st.caption("流程：實價登錄(合法) → 清理 → PRR。\n生產環境對應 Kafka → Spark → DB。"
               "591/樂居因 ToS 不由公開按鈕觸發。")

st.title("🌡️ 房價溫度計 HouseTherm")
st.caption("雙北買房決策輔助 · 資料：內政部實價登錄 · "
           "PRR = 房價 / 年租金（越高代表相對租金越貴；租金收益率 = 1/PRR）")
st.success(f"🔎 **資料可信度**：基於 **{len(tx):,}** 筆實價登錄成交（雙北 "
           f"{trend.index.min()}–{trend.index.max()}）· 已分房型 / 排除車位 / 踢非市場交易 / IQR 去極端 · "
           f"PRR 自 112S4 起算（租賃實價登錄涵蓋）。")

# ---------- 選擇：城市 → 行政區 → 房型 ----------
c1, c2, c3 = st.columns(3)
city = c1.selectbox("城市", sorted(dist["city"].unique()))
csub = dist[dist["city"] == city]
d = c2.selectbox("行政區", sorted(csub["鄉鎮市區"].unique()))
dsub = csub[csub["鄉鎮市區"] == d].sort_values("PRR(年)", ascending=False)
htype = c3.selectbox("房型", dsub["房型"])
row = dsub[dsub["房型"] == htype].iloc[0]
type_median = dist[dist["房型"] == htype]["PRR(年)"].median()

# ---------- 溫度 metrics ----------
st.subheader(f"📍 {city} {d}・{htype}")
m = st.columns(4)
m[0].metric("買賣中位", f'{row["買賣中位(萬/坪)"]} 萬/坪')
m[1].metric("月租中位", f'{row["月租中位(元/坪)"]:.0f} 元/坪')
m[2].metric("PRR 房價租金比", f'{row["PRR(年)"]} 年')
m[3].metric("租金收益率", f'{row["租金收益率%"]}%')

diff = row["PRR(年)"] - type_median
base = f"（同為「{htype}」雙北中位 {type_median:.1f} 年）"
if diff > 3:
    st.error(f"🔴 偏熱：此區{htype} PRR {row['PRR(年)']} 年 ＞ {base}，相對租金偏貴。")
elif diff < -3:
    st.success(f"🔵 偏冷：此區{htype} PRR {row['PRR(年)']} 年 ＜ {base}，相對租金較划算。")
else:
    st.warning(f"🟡 中性：此區{htype} PRR {row['PRR(年)']} 年 ≈ {base}。")

# ---------- 進場時機燈號 (A) ----------
mom_sel = get_mom(city, d, htype)
light, advice = timing_light(row["PRR(年)"], type_median, mom_sel)
mom_txt = f"近半年房價 {mom_sel:+.0f}%" if mom_sel is not None else "近半年動能資料不足"
st.subheader(f"🚦 進場時機：{light}")
st.markdown(f"> **{advice}**　（估值 PRR {row['PRR(年)']:.0f} vs 同型中位 {type_median:.0f}；{mom_txt}）")

# ---------- 現在 vs 過去 ----------
st.subheader("📈 現在 vs 過去")
if city in trend.columns:
    s = trend[city].dropna()
    latest, pct = s.iloc[-1], (s < s.iloc[-1]).mean() * 100
    st.write(f"**{city}** 最新季 **{latest} 萬/坪**，高於過去 **{pct:.0f}%** 的季別"
             f"（4 年區間 {s.min()}–{s.max()} 萬/坪）。")
    st.line_chart(s, height=260)

# ---------- 用租金判斷：房價 vs 租金 走勢與背離 (#2) ----------
st.subheader("📐 用租金判斷：房價 vs 租金 走勢與背離")
tp = panel[(panel["city"] == city) & (panel["鄉鎮市區"] == d)
           & (panel["房型"] == htype)].sort_values("skey")
tpr = tp.dropna(subset=["prr"])
if len(tp) >= 4 and len(tpr) >= 3:
    prr_now, prr_med, prr_peak = tpr["prr"].iloc[-1], tpr["prr"].median(), tpr["prr"].max()
    peak_season = tpr.loc[tpr["prr"].idxmax(), "season"]
    a = st.columns(3)
    a[0].metric("目前 PRR", f"{prr_now:.0f} 年")
    a[1].metric("自身歷史中位", f"{prr_med:.0f} 年", delta=f"{prr_now - prr_med:+.0f}")
    a[2].metric("歷史高點", f"{prr_peak:.0f} 年", help=f"出現於 {peak_season}")

    fig, axL = plt.subplots(figsize=(8, 3.2))
    axR = axL.twinx()
    l1, = axL.plot(tp["season"], tp["price_pp"], "o-", color="#c0392b", label="房價(萬/坪)")
    l2, = axR.plot(tp["season"], tp["rent_pp"], "s--", color="#2980b9", label="租金(元/坪/月)")
    axL.set_ylabel("房價 萬/坪", color="#c0392b")
    axR.set_ylabel("租金 元/坪/月", color="#2980b9")
    axL.tick_params(axis="x", rotation=90)
    axL.grid(alpha=0.3)
    axL.legend(handles=[l1, l2], loc="upper left", fontsize=8)
    fig.tight_layout()
    st.pyplot(fig)

    pc = pct_change(tp.set_index("season")["price_pp"])
    rc = pct_change(tp.set_index("season")["rent_pp"])
    lead = "、".join(p for p in [
        f"近一年房價 {pc:+.0f}%" if pc is not None else None,
        f"租金 {rc:+.0f}%" if rc is not None else None] if p)
    tag = ""
    if pc is not None and rc is not None:
        if pc > 3 and rc <= 1:
            tag = "房價漲幅明顯超過租金 → PRR 被推升、偏離基本面（偏貴）。"
        elif rc < -2 and pc <= 1:
            tag = "租金走弱但房價僵固 → 估值僵在高檔，**易鬆動**（下修壓力）。"
        elif pc < 0 and prr_now < prr_med:
            tag = "房價回落且 PRR 低於自身中位 → 相對回到合理區間。"
        else:
            tag = "房價與租金大致同向，PRR 相對穩定。"
    val = ("目前 PRR 高於自身歷史中位，**估值偏高檔**。" if prr_now > prr_med * 1.05
           else "目前 PRR 低於自身歷史中位，**估值相對便宜**。" if prr_now < prr_med * 0.95
           else "目前 PRR 約在自身歷史中位。")
    st.info(f"{lead}。{tag} {val}")
else:
    st.caption("（此區此房型逐季租金樣本不足，難算 PRR 走勢；租賃實價登錄約 2024 起才較完整。）")

# ---------- 哪裡相對不會買貴 (#3) ----------
st.subheader("🏷️ 哪裡相對不會買貴？（正在降溫 + 相對便宜）")
rc1, rc2 = st.columns(2)
types = sorted(screen["房型"].unique())
rtype = rc1.selectbox("房型", types, index=types.index(htype) if htype in types else 0, key="rtype")
scope = rc2.radio("範圍", ["雙北", city], horizontal=True)
sc = screen[screen["房型"] == rtype].copy()
if scope != "雙北":
    sc = sc[sc["city"] == scope]
cool = sc["近半年漲跌%"] < 0
cheap = sc["目前PRR"] < sc["同房型跨區PRR中位"]
rec = sc[cool & cheap].sort_values("近半年漲跌%")
if len(rec):
    st.success("✅ 建議優先看（降溫中且相對便宜）：" +
               "、".join(f'{r.city}{r["鄉鎮市區"]}' for _, r in rec.head(6).iterrows()))
disp = sc.assign(降溫中=cool.map({True: "🟢", False: ""}), 相對便宜=cheap.map({True: "💰", False: ""}))
disp = disp.sort_values(["近半年漲跌%", "目前PRR"])
st.dataframe(disp[["city", "鄉鎮市區", "現價(萬/坪)", "近半年漲跌%", "近一年漲跌%",
                   "目前PRR", "同房型跨區PRR中位", "降溫中", "相對便宜"]],
             hide_index=True, use_container_width=True, height=300)
st.caption("『🟢降溫中』=近半年房價動能為負；『💰相對便宜』=目前 PRR 低於同房型跨區中位。"
           "此為篩選訊號，個別物件仍需查證屋況、生活機能與重大建設。")

# ---------- 評估開價 + 比價 (#5) ----------
st.subheader("🔍 這個開價合理嗎？（與該區同房型實際成交比價）")
e1, e2, e3, e4 = st.columns(4)
price = e1.number_input("物件總價（萬元）", value=2000, step=50)
size = e2.number_input("權狀坪數", value=25.0, step=1.0, min_value=1.0)
tol = e3.number_input("坪數範圍 ±", value=5.0, step=1.0, min_value=0.0)
years_all = sorted(tx["season"].str[:3].astype(int).unique())
ly = years_all[-1]
period_opts = {f"近2年 ({ly - 1}–{ly})": (ly - 1, ly),
               f"前2年 ({ly - 3}–{ly - 2})": (ly - 3, ly - 2),
               "全部": (years_all[0], ly)}
psel = e4.selectbox("成交期間", list(period_opts))
ylo, yhi = period_opts[psel]
ppp = price / size

gap = (ppp - row["買賣中位(萬/坪)"]) / row["買賣中位(萬/坪)"] * 100
implied_prr = ppp / (row["月租中位(元/坪)"] * 12 / 10000)
st.write(f"每坪單價 **{ppp:.1f} 萬/坪**，{d}「{htype}」行情中位 {row['買賣中位(萬/坪)']} 萬/坪 → "
         f"**{'高於' if gap >= 0 else '低於'}行情 {abs(gap):.0f}%**；隱含 PRR ≈ **{implied_prr:.0f} 年**。")

comps = get_comps(city, d, htype, size, tol, ylo, yhi)        # 坪數區間 + 期間（表格）
stat = comps if len(comps) >= 20 else get_comps(city, d, htype, size, 9e9, ylo, yhi)  # 百分位（不足放寬坪數）
if len(stat) >= 20:
    p_rank = (stat["每坪價萬"] < ppp).mean() * 100
    q1, q2, q3 = stat["每坪價萬"].quantile([0.25, 0.5, 0.75])
    nego = max(0.0, (ppp - q2) / ppp * 100)
    st.write(f"在 **{psel}**、該區「{htype}」**{len(stat):,}** 筆成交中，此開價落在第 **{p_rank:.0f} 百分位**。")
    st.write(f"💬 **議價空間**：合理成交區間約 **{q1:.0f}–{q3:.0f} 萬/坪**（P25–P75），建議目標 ≈ 中位 "
             f"**{q2:.0f} 萬/坪**"
             + (f"，此開價可議幅度約 **{nego:.0f}%**。" if nego > 1 else "，此開價已接近或低於行情中位。"))
    cc1, cc2 = st.columns([3, 2])
    with cc1:
        fig, ax = plt.subplots(figsize=(6, 3))
        lo, hi = stat["每坪價萬"].quantile([0.01, 0.99])
        ax.hist(stat["每坪價萬"].clip(lo, hi), bins=30, color="#3498db", alpha=0.8)
        ax.axvline(ppp, color="#c0392b", lw=2, label=f"你的開價 {ppp:.0f}")
        ax.axvline(stat["每坪價萬"].median(), color="gray", ls="--", lw=1.5, label="行情中位")
        ax.set_xlabel("每坪價（萬）"); ax.set_ylabel("成交筆數"); ax.legend()
        st.pyplot(fig)
    with cc2:
        mid = f"，每坪中位 {comps['每坪價萬'].median():.0f} 萬" if len(comps) else ""
        st.caption(f"{psel}、{size:.0f}±{tol:.0f} 坪 成交（{len(comps)} 筆{mid}）：")
        st.dataframe(comps.head(15)[["season", "地址", "坪數", "總價萬", "每坪價萬"]],
                     hide_index=True, use_container_width=True, height=360)
else:
    st.caption(f"（該區該房型於 {psel} 成交樣本不足，難以比價；可改『全部』或放寬坪數範圍）")

# ---------- 貸款試算（多方案）----------
st.subheader("💰 貸款月付試算（多種貸款方案）")
prod = st.selectbox("貸款種類", list(PRODUCTS.keys()))
p = PRODUCTS[prod]
is_credit = prod.startswith("信用貸款")
g1, g2 = st.columns(2)
with g1:
    rate = st.number_input("利率 (%)", value=p["rate"] * 100, step=0.05, key="rate") / 100
    yrs = st.slider("貸款年限（年）", 1, 40, p["years"], key="yrs")
    grace = st.slider("寬限期（年，只繳息）", 0, 5, p["grace"], key="grace")
    if is_credit:
        loan_wan = st.number_input("貸款金額（萬元）", value=200, step=10,
                                   max_value=p["cap_wan"], key="cl")
        res = {"loan_wan": loan_wan, "down_payment_wan": None,
               "capped_ltv": False, "capped_amt": False,
               **monthly_payment(loan_wan * 10000, rate, yrs, grace)}
    else:
        lp = st.number_input("房屋總價（萬元）", value=int(price), step=50, key="lp")
        default_down = int((1 - p["ltv"]) * 100) if p["ltv"] else 20
        down = st.slider("自備款成數 (%)", 10, 60, default_down, key="down") / 100
        res = mortgage(lp, down_ratio=down, rate=rate, years=yrs, grace=grace,
                       cap_wan=p["cap_wan"], ltv=p["ltv"])
with g2:
    notes = []
    if res["capped_amt"]:
        notes.append(f"達額度上限 {p['cap_wan']} 萬")
    if res["capped_ltv"]:
        notes.append(f"受最高 {int(p['ltv'] * 100)} 成限制")
    st.metric("貸款金額", f'{res["loan_wan"]:,} 萬' + (f"（{'、'.join(notes)}）" if notes else ""))
    if res["down_payment_wan"] is not None:
        st.metric("實際自備款", f'{res["down_payment_wan"]:,} 萬')
    if grace > 0:
        st.metric(f"寬限期月付（前 {grace} 年只繳息）", f'{res["grace_monthly"]:,} 元')
    st.metric("正常月付（本息均攤）", f'{res["normal_monthly"]:,} 元')
    st.metric("總利息", f'{res["total_interest_wan"]:,} 萬')
st.caption(f"**{prod}**：{p['note']} 利率/條件為示意預設，請以承貸行庫公告為準。")

# ---------- 可負擔性反推 (C) ----------
st.subheader("🔄 可負擔性反推：我買得起哪裡？")
af1, af2, af3 = st.columns(3)
income = af1.number_input("家庭月收入（萬元）", value=10.0, step=0.5, min_value=1.0)
burden = af2.slider("房貸佔收入比 (%)", 20, 50, 33)
own_pay = af3.number_input("自備款（萬元）", value=300, step=50)
afford_monthly = income * 10000 * burden / 100
maxloan_wan = min(max_loan_from_payment(afford_monthly, PRODUCTS["新青安"]["rate"], 30) / 10000,
                  PRODUCTS["新青安"]["cap_wan"])
afford_total = own_pay + maxloan_wan
st.write(f"月付上限 **{afford_monthly:,.0f} 元**（新青安 1.775%/30年、貸款上限1000萬）+ 自備 {own_pay} 萬 "
         f"→ 可負擔總價約 **{afford_total:,.0f} 萬**。")
want_size = st.slider("想要的坪數", 10, 60, 25)
afford_pp = afford_total / want_size
elig = dist[dist["房型"] == htype].copy()
elig["買得起?"] = (elig["買賣中位(萬/坪)"] <= afford_pp).map({True: "✅", False: ""})
st.write(f"買 **{want_size} 坪** 的「{htype}」→ 每坪需 ≤ **{afford_pp:.0f} 萬**：")
st.dataframe(elig.sort_values("買賣中位(萬/坪)")[
    ["city", "鄉鎮市區", "買賣中位(萬/坪)", "PRR(年)", "買得起?"]],
    hide_index=True, use_container_width=True, height=260)

# ---------- 公道價一頁報告 (B) ----------
st.subheader("📄 公道價一頁報告（可下載列印給客戶/自用）")
rep = mortgage(price, 0.2, PRODUCTS["新青安"]["rate"], 30, 0,
               PRODUCTS["新青安"]["cap_wan"], PRODUCTS["新青安"]["ltv"])
rep_comps = get_comps(city, d, htype, size, tol, ly - 1, ly)                       # 近2年 + 坪數區間
rep_stat = rep_comps if len(rep_comps) >= 20 else get_comps(city, d, htype, size, 9e9, ly - 1, ly)
if len(rep_stat) >= 20:
    rq1, rq2, rq3 = rep_stat["每坪價萬"].quantile([0.25, 0.5, 0.75])
    rrank = (rep_stat["每坪價萬"] < ppp).mean() * 100
    rnego = max(0.0, (ppp - rq2) / ppp * 100)
    band = (f"{rq1:.0f}–{rq3:.0f} 萬/坪（P25–P75），中位 {rq2:.0f}；"
            f"此開價第 {rrank:.0f} 百分位，可議約 {rnego:.0f}%")
else:
    band = "可比成交不足"
comps_html = "".join(
    f"<tr><td style='text-align:left'>{r['地址']}</td><td>{r['season']}</td>"
    f"<td>{r['坪數']:.0f}</td><td>{r['總價萬']:.0f}</td><td>{r['每坪價萬']:.0f}</td></tr>"
    for _, r in rep_comps.head(15).iterrows())
asof = date.today().isoformat()
report_html = f"""<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>
<title>公道價報告 {city}{d}{htype}</title><style>
body{{font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;max-width:720px;margin:24px auto;color:#222}}
h1{{font-size:20px}} .k{{color:#888}} table{{border-collapse:collapse;width:100%;margin:8px 0}}
td,th{{border:1px solid #ddd;padding:4px 8px;font-size:13px;text-align:right}} th{{background:#f4f4f4}}
.box{{background:#f7f9fb;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;margin:8px 0;font-size:14px}}
.foot{{color:#999;font-size:11px;margin-top:16px}}</style></head><body>
<h1>🌡️ 房價溫度計 · 物件評估報告</h1>
<p class='k'>{city} {d}・{htype}　|　產生日期 {asof}</p>
<div class='box'><b>物件</b>：總價 {price:,.0f} 萬 / {size:.0f} 坪 = 每坪 <b>{ppp:.1f} 萬</b></div>
<div class='box'><b>行情比較</b>：{d}「{htype}」中位 {row['買賣中位(萬/坪)']} 萬/坪，
此開價{'高' if gap >= 0 else '低'}於行情 <b>{abs(gap):.0f}%</b>；隱含 PRR ≈ <b>{implied_prr:.0f} 年</b>
（同型雙北中位 {type_median:.0f}）。</div>
<div class='box'><b>議價空間</b>：{band}。</div>
<div class='box'><b>進場時機</b> {light}：{advice}</div>
<div class='box'><b>新青安月付</b>（總價8成/上限1000萬/30年）：貸 {rep['loan_wan']:,} 萬、
自備 {rep['down_payment_wan']:,} 萬、月付 <b>{rep['normal_monthly']:,} 元</b>。</div>
{(f"<b>近兩年可比成交（{size:.0f}±{tol:.0f} 坪，共 {len(rep_comps)} 筆，列前 15）</b>"
  "<table><tr><th style='text-align:left'>地址</th><th>季</th><th>坪</th><th>總價(萬)</th><th>每坪(萬)</th></tr>"
  + comps_html + "</table>") if comps_html else ""}
<p class='foot'>資料來源：內政部實價登錄（雙北 {trend.index.min()}–{trend.index.max()}，共 {len(tx):,} 筆，
分房型/排除車位/踢非市場交易/IQR 去極端）。本報告為市場行情參考，非估價或投資建議。</p></body></html>"""
st.download_button("⬇️ 下載報告（HTML，可用瀏覽器列印成 PDF）", data=report_html,
                   file_name=f"房價報告_{city}{d}{htype}.html", mime="text/html")
with st.expander("預覽報告內容"):
    components.html(report_html, height=560, scrolling=True)

# ---------- 政策與風險訊號 (#4) ----------
st.subheader("🧭 政策與風險訊號（未來房價怎麼走？）")
jump = monthly_payment(10_000_000, DEFAULTS["annual_rate"], 30, grace_years=5)
ratio = jump["normal_monthly"] / jump["grace_monthly"]
p1, p2 = st.columns(2)
with p1:
    st.markdown(
        "**⬆️ 推升力（需求拉動）**\n"
        "- 新青安補貼大幅壓低首購月付門檻，拉抬需求，尤其 **1000 萬以下** 總價帶。\n\n"
        "**⬇️ 下修風險**\n"
        "- 央行選擇性信用管制：第二屋限貸、無寬限、法人從嚴 → 打投資/換屋需求。\n"
        "- **量先價行**：信用管制後交易量萎縮，歷史上量縮領先價跌。\n"
        "- **新青安斷頭風險**：5 年寬限到期月付暴增（見右）。\n"
        "- 機動利率：郵儲利率上行則月付再加重。")
with p2:
    st.markdown("**🔥 新青安斷頭壓力試算**（1000 萬 / 30 年 / 寬限 5 年）")
    j1, j2 = st.columns(2)
    j1.metric("寬限期月付", f'{jump["grace_monthly"]:,} 元')
    j2.metric("到期後月付", f'{jump["normal_monthly"]:,} 元', delta=f'×{ratio:.1f}')
    st.caption(f"寬限到期後月付跳升約 **{ratio:.1f} 倍**。2023H2 放款潮約於 2028–2029 集中到期，"
               "若所得撐不住者集中拋售，恐形成區域性供給壓力。")
st.info("綜合判讀：**短期**補貼撐住蛋白區與千萬以下；**中期(2028~)** 量縮 + 寬限到期 + 升息敏感，"
        "高槓桿首購族最脆弱；估值面雙北 PRR 偏高（收益率 <2%），需求轉弱即有修正空間。")

# ---------- 地圖 (#3) ----------
st.subheader(f"🗺️ {city}「{htype}」各區地圖")
basis = st.radio("地圖顏色依據", ["PRR（貴不貴）", "近半年漲跌（降溫沒）"], horizontal=True)
mp = dist[(dist["city"] == city) & (dist["房型"] == htype)].merge(
    screen[["city", "鄉鎮市區", "房型", "近半年漲跌%"]],
    on=["city", "鄉鎮市區", "房型"], how="left").rename(
    columns={"PRR(年)": "prr", "買賣中位(萬/坪)": "price", "近半年漲跌%": "mom"})
mp["lat"] = mp["鄉鎮市區"].map(lambda x: DISTRICT_LATLON.get(x, (None, None))[0])
mp["lon"] = mp["鄉鎮市區"].map(lambda x: DISTRICT_LATLON.get(x, (None, None))[1])
mp = mp.dropna(subset=["lat", "lon"]).copy()
if len(mp):
    if basis.startswith("PRR"):
        center = dist[dist["房型"] == htype]["PRR(年)"].median()
        half = (mp["prr"] - center).abs().max() or 1
        hexes = mp["prr"].map(lambda v: div_hex(v, center, half))
        cap = f"🔴 紅=PRR 高於同型中位({center:.0f})、相對偏貴　🟢 綠=低於中位、相對便宜"
    else:
        vals = mp["mom"].fillna(0)
        half = vals.abs().max() or 1
        hexes = vals.map(lambda v: div_hex(v, 0, half))
        cap = "🔴 紅=近半年上漲(偏熱)　🟢 綠=近半年下跌(降溫)"
    mp["fill"] = hexes.map(lambda h: [int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 200])
    mp["radius"] = (mp["price"] * 6).clip(250, 700)
    mp["prr"] = mp["prr"].round(0)
    mp["price"] = mp["price"].round(0)
    mp["mom"] = mp["mom"].fillna(0).round(1)
    view = pdk.data_utils.compute_view(mp[["lon", "lat"]])
    view.zoom = max(view.zoom - 0.4, 9)
    layer = pdk.Layer("ScatterplotLayer", data=mp, get_position=["lon", "lat"],
                      get_fill_color="fill", get_radius="radius", pickable=True,
                      stroked=True, get_line_color=[70, 70, 70], line_width_min_pixels=1)
    tooltip = {"html": "<b>{鄉鎮市區}</b>（{房型}）<br/>PRR {prr} 年<br/>每坪 {price} 萬<br/>近半年 {mom}%"}
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view,
                             map_provider="carto", map_style="road", tooltip=tooltip))
    st.caption(cap + "；圈大小=每坪房價；滑鼠移到圈上看數字。")
    st.info("ℹ️ 『PRR(貴不貴)』與『漲跌(降溫沒)』是兩個不同維度——"
            "一個區可能**估值偏高但正在降溫**（如中和大樓），兩張圖一起看最準。")

# ---------- 各區 PRR（同房型橫向比較）----------
st.subheader(f"📊 {city}「{htype}」各區 PRR 比較")
typ_sub = (dist[(dist["city"] == city) & (dist["房型"] == htype)]
           .sort_values("PRR(年)", ascending=False))
st.bar_chart(typ_sub.set_index("鄉鎮市區")["PRR(年)"], height=380)

# ---------- 贊助 / donate ----------
st.divider()
st.markdown(
    "☕ **覺得有幫助嗎？** 本工具的金流除了「房仲訂閱 + 公道價報告服務」，也歡迎小額贊助："
    "[**Buy Me a Coffee**](https://www.buymeacoffee.com/justforverlove) 支持資料持續更新與新功能開發。")
st.caption("資料來源：內政部實價登錄（雙北）· 本工具為市場行情參考，非估價或投資建議。")
