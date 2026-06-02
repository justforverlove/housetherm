# 房價溫度計 HouseTherm — 雙北買房決策輔助平台

> Big Data Systems Final Project · NTU Spring 2026
> 用「租金」當錨點，幫雙北自住買房族判斷：現在房價偏高還偏低、用新青安買要付多少、
> 以及有哪些領先指標顯示未來下修風險。

**Report (PDF):** `P13922002.pdf`
**GitHub:** `https://github.com/justforverlove/housetherm`
**Live Demo (bonus):** `https://housetherm-bczk9hmmigrxh74m24aep7.streamlit.app`

---

## 1. What it does

幫想在**雙北買房自住**的人回答三個問題：

- 🌡️ **現在貴不貴？** 用房價租金比 (Price-to-Rent Ratio) + 房價歷史百分位，把開價放回歷史與租金基本面比較。
- 📉 **未來會不會跌？** 不做黑盒預測 —— 用**透明風險訊號儀表板**整合領先指標（PRR 偏離、交易量、法拍量、利率、政策），讓買方自行評估時機風險。
- 💰 **我買得起嗎？** 新青安 (新青年安心成家貸款) 月付試算 + 貸款負擔率。

**Target customer（雙邊市場）:**
- **房仲（B2B，付費主力）**：以信任/透明差異化的業務，用客觀數據對客戶證明「開價合理、沒騙人」→ 加速成交。
- **購屋族（B2C，引流）**：雙北首購 / 自住買房族，尤其考慮新青安的人，當買屋參考。

---

## 2. 核心分析：房價租金比 (Price-to-Rent Ratio)

```
PRR = 每坪房價 / 每坪年租金          租金收益率 = 1 / PRR
```

- 雙北 PRR 出名地高（租金收益率常僅 1.5%–2.5%，PRR 約 40–60 倍）→ 量化「房價相對租金基本面偏貴」。
- 把某物件開價換算成「幾年租金回本」，再跟該區歷史、跟其他行政區比較 → **直接看出貴不貴**。
- 租金資料（591）= 估值的分母；成交價（實價登錄）= 分子。

---

## 3. Architecture (Lambda)

```
  Data Sources              Ingestion           Processing                 Serving           Delivery
┌────────────────┐       ┌────────────┐   ┌──────────────────┐      ┌──────────────┐   ┌──────────────┐
│ 實價登錄(成交價)│       │            │   │ Batch Layer      │      │ PostgreSQL   │   │ 房價溫度計    │
│ 591 (租金)     │──────▶│ Scrapers ─▶│──▶│ Spark batch      │─────▶│ (歷史/行情)  │──▶│ Dashboard    │
│ ── Phase 2 ──  │       │  Kafka     │   │ PRR / 歷史百分位 │      │ Redis        │   │ 新青安試算    │
│ 法拍/新聞/利率 │       │            │   ├──────────────────┤      │ (即時 hot)   │   │ REST API     │
└────────────────┘       └────────────┘   │ Speed Layer (P2) │─────▶│ MinIO        │   │ 風險訊號警示  │
                                          │ 新聞/政策事件警示 │      │ (原始 CSV)   │   └──────────────┘
                                          └──────────────────┘      └──────────────┘
```

| 層 | 技術 | 為什麼 |
|----|------|--------|
| Message Queue | **Kafka** | 解耦爬蟲與處理，可重播、可擴展 |
| Batch Layer | **Spark (batch)** | 大量歷史成交/租金的 PRR、百分位、趨勢計算 |
| Speed Layer (Phase 2) | **Spark Structured Streaming** | 新聞/政策/利率事件即時警示 |
| Hot Store | **Redis** | 即時查詢各區最新溫度與訊號 |
| Cold Store | **PostgreSQL** | 結構化歷史成交/租金/指標 (SQL 查詢) |
| Raw Store | **MinIO** (S3 相容) | 原始季度 CSV / 爬蟲快照 (data lake) |
| Delivery | **FastAPI + Streamlit/React** | Dashboard + 新青安試算 + 訂閱 API |

> 學生專案可用 `docker-compose` 單機跑全部服務；重點是架構說清楚、能 demo。

---

## 4. Repository structure

```
housetherm/
├── README.md
├── docker-compose.yml         # Kafka/Spark/Redis/Postgres/MinIO 一鍵啟動
├── .env.example
├── requirements.txt
│
├── docs/
│   ├── architecture.png       # 架構圖（PDF 報告共用）
│   └── data_dictionary.md     # 各資料源欄位說明
│
├── ingestion/                 # 資料蒐集
│   ├── scrapers/
│   │   ├── lvr_gov.py         # 實價登錄季度 CSV（主，合法）— 雙北
│   │   ├── rent591.py         # 591 租金（輔，含限速 / ToS 註記）
│   │   └── phase2/
│   │       ├── foreclosure.py # 司法院法拍量（Phase 2）
│   │       ├── news.py        # 房市新聞/政策事件（Phase 2）
│   │       └── rates.py       # 央行利率/信用管制（Phase 2）
│   ├── kafka_producer.py
│   └── README.md              # 如何重現資料蒐集（評分要求）
│
├── processing/
│   ├── batch/
│   │   ├── prr.py             # 房價租金比計算（每區/每類型）
│   │   ├── price_index.py     # 房價歷史百分位 / 趨勢
│   │   └── affordability.py   # 房價所得比 / 貸款負擔率
│   ├── speed/
│   │   └── event_alerts.py    # 新聞/政策事件警示（Phase 2）
│   └── schemas/
│       └── transaction.py     # 成交/租金 schema（共用）
│
├── storage/
│   ├── postgres/init.sql      # 建表 / 索引
│   └── redis/keys.md          # key 設計
│
├── delivery/
│   ├── api/main.py            # FastAPI：估值 / 訊號 / 試算端點
│   ├── dashboard/app.py       # 房價溫度計前端
│   ├── calculator/loan.py     # 新青安月付試算邏輯
│   └── notifier/alerts.py     # 風險訊號警示（Phase 2）
│
├── analysis/                  # 需求驗證（Component 2，評分 25%）
│   ├── demand_validation.ipynb  # PRR 現況、房價趨勢、痛點量化
│   ├── competitor_pricing.md    # 競品(實價登錄Pro/樂居/591實價) 定價
│   └── survey/
│       ├── questions.md         # 訪談/問卷題目
│       └── responses_summary.md # 回應摘要
│
├── data/samples/              # 範例資料（小量，供 grader 重現）
└── tests/test_pipeline.py
```

---

## 5. 你實際要做的事（對應 rubric）

| 工作 | 對應評分 | 產出位置 | 階段 |
|------|---------|---------|------|
| ① 需求驗證：爬雙北實價登錄、算 PRR、找競品定價、PTT/Dcard 痛點、訪談 | **25%** | `analysis/` | 先做 |
| ② 目標客戶定義（雙北首購族）與 wedge 論述 | **20%** | 報告 | 先做 |
| ③ pipeline：實價登錄+591 → Kafka → Spark batch(PRR/百分位) → DB → dashboard | **40%** | `ingestion/` `processing/` `storage/` `delivery/` | Phase 1 |
| ④ 新青安月付試算 | （含 40%） | `delivery/calculator/` | Phase 1 |
| ⑤ 風險訊號儀表板（法拍量/新聞/利率 + stream） | （含 40%） | `*/phase2/` | Phase 2 |
| ⑥ 架構圖、README、報告寫作 | **15%** | `docs/` 報告 | 全程 |
| ⑦ (Bonus) Go-to-market 困難分析 | +10% | 報告 | 後期 |
| ⑧ (Bonus) 線上部署 | +10% | 部署平台 | 後期 |

---

## 6. Quick start

```bash
# 1. 啟動基礎設施
cp .env.example .env
docker-compose up -d        # Kafka, Spark, Redis, Postgres, MinIO

# 2. 初始化資料庫
psql -h localhost -U housetherm -f storage/postgres/init.sql

# 3. 資料蒐集（先從合法的實價登錄開始，雙北）
python ingestion/scrapers/lvr_gov.py --cities 台北市 新北市
python ingestion/scrapers/rent591.py --cities 台北市 新北市
python ingestion/kafka_producer.py

# 4. 批次處理：算 PRR、房價歷史百分位
spark-submit processing/batch/prr.py
spark-submit processing/batch/price_index.py

# 5. 啟動服務
uvicorn delivery.api.main:app --reload
streamlit run delivery/dashboard/app.py
```

---

## 7. 重現需求驗證 (Reproducing demand evidence)

評分明確要求「scripts for reproducing any data-collection step」：

```bash
jupyter nbconvert --execute analysis/demand_validation.ipynb
# 產生：雙北各區 PRR 現況、房價歷史百分位、交易量趨勢、痛點量化圖
```

詳見 [`ingestion/README.md`](ingestion/README.md) 與 [`analysis/`](analysis/)。

---

## 8. 重要設計原則

- **不預測價格**：系統整合 PRR 偏離、交易量（量先價行）、法拍量、利率、政策等**領先指標**供買方判斷，不輸出黑盒預測。
- **「融資斷頭」** 以**法拍屋量上升**當代理指標；**「政府補救」** 以新青安調整、央行信用管制事件呈現。
- **資料倫理**：主資料源為內政部實價登錄（政府開放資料，合法可重發）；591/新聞僅作研究，遵守 robots.txt、限速、不重發原文；報告誠實討論 ToS 與 PDPA（Go-to-Market 加分）。

---

## 9. Roadmap

- [ ] 需求驗證（雙北實價登錄爬蟲 + PRR 現況 + 競品定價 + 痛點量化）
- [ ] Phase 1 end-to-end（實價登錄+591 → PRR/百分位 → dashboard + 新青安試算）
- [ ] Phase 2 風險訊號（法拍量 + 新聞/政策 stream 警示）
- [ ] (Bonus) 部署 + Go-to-market 分析
- [ ] 寫 PDF 報告（最後）
