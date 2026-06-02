# HouseTherm (房價溫度計): A Rent-Anchored Decision-Support System for Home Buyers in Greater Taipei

**Big Data Systems — Final Project · National Taiwan University · Spring 2026**

| | |
|---|---|
| **Student ID** | P13922002 |
| **GitHub repository** | `https://github.com/<your-account>/housetherm` |
| **Live demo** | `https://<your-app>.streamlit.app`  *(or Cloud Run URL)* |
| **Date** | 2026-06-02 |

---

## 1. Overview

Raw real-estate data is abundant and public in Taiwan, yet a first-time buyer still cannot
easily answer three questions: *Is this listing expensive? Will prices fall? Can I afford it?*
**HouseTherm** turns the government's open **Actual Price Registration (實價登錄, LVR)** data into a
decision-support product for buyers and real-estate agents in **Taipei City and New Taipei City
(雙北)**.

The analytical backbone is the **Price-to-Rent Ratio (PRR)** — the same dataset contains *both* sale
and rental transactions, so we can anchor every sale price to what the same kind of property earns
as rent. This bridges "technical capability" and "economic value": the system is technically a
data pipeline, but its value proposition is *judgement* — telling a user whether a price is
defensible against rental fundamentals and historical trend.

---

## 2. Target Customer (Required Component 1)

HouseTherm serves a **two-sided market**:

**(a) Real-estate agents / pre-sale sales teams (房仲 / 代銷) — the paying side (B2B).**
Agents who differentiate on *trust* (brand agencies, buyer's agents, salespeople facing
price-skeptical clients) can use objective LVR-based evidence to show a client "this asking price
is reasonable — here is the data," shortening negotiation and closing faster. The product is a
**sales-enablement tool**: a one-page, exportable *fair-price report*.

**(b) Home buyers (購屋族) — the lead-generation side (B2C).**
First-time, owner-occupier buyers in 雙北 — especially those considering the government's
**新青安 (New Youth Housing Loan)** — use the dashboard as a reference: is the area expensive, is it
cooling, what can I afford. They are served free to build word-of-mouth and credibility, which in
turn makes the tool more persuasive for agents.

**Why this wedge.** Buyers in 雙北 face the most extreme affordability gap in Taiwan and the most
public discussion (PTT *home-sale*, Dcard, 新青安 threads), so demand is easy to evidence. Agents
have real willingness to pay because the tool directly helps them close. We explicitly *do not*
target "everyone who buys property"; the wedge is **trust-first agents + 雙北 first-time buyers**.

**An honest tension (good go-to-market material).** The tool can label a listing "expensive,"
which may discourage a sale — so not every agent wants it. Our customer is the subset that competes
on transparency. This conflict of interest is analysed in §6.

---

## 3. Evidence of Demand and Willingness to Pay (Required Component 2)

We followed the project's guidance to *validate before building* and to *document the full
process, not just the conclusion*. All steps are reproducible (§9).

### 3.1 Data-acquisition process

1. **Source.** Ministry of the Interior LVR open data, bulk seasonal download endpoint
   `https://plvr.land.moi.gov.tw/DownloadSeason`. This is government open data, legally
   re-usable. We download city `a` (Taipei) and `f` (New Taipei), file type `a`
   (sale) and `c` (rental). Script: [`ingestion/scrapers/lvr_gov.py`](ingestion/scrapers/lvr_gov.py)
   (with caching; unreleased quarters skipped automatically).
2. **Coverage.** 17 quarters, **111S1–115S1 (2022 Q1 – 2026 Q1)**:
   **344,626** sale records + **161,246** rental records.
3. **Cleaning** ([`analysis/prr_validation.py`](analysis/prr_validation.py)) → **228,767** sale +
   **56,176** whole-floor rental records:
   - split by building type → **大樓 / 華廈 / 公寓 / 透天** (mixing types distorts medians, e.g. old
     walk-ups blending into apartment-tower prices);
   - compute a **parking-excluded** unit price `(total − parking price) / (area − parking area)`;
   - drop **non-arm's-length** deals (notes flagging related-party / debt-relief / auction);
   - keep residential use only; for rent keep **whole-floor** leases (matching "buy a whole unit");
   - **IQR** outlier trimming per (city × district × type) group.

### 3.2 Finding 1 — prices are expensive relative to rent (the thesis holds)

| City | Type | Median sale | PRR (yrs) | Rental yield |
|---|---|---|---|---|
| Taipei | Apartment tower (大樓) | 82.3 萬/坪 | 44.9 | 2.23% |
| Taipei | Walk-up (公寓) | 58.7 萬/坪 | 52.3 | 1.91% |
| New Taipei | Apartment tower (大樓) | 46.3 萬/坪 | 59.6 | 1.68% |
| New Taipei | Walk-up (公寓) | 37.9 萬/坪 | 43.4 | 2.30% |

A healthy rental yield is ~4–5%; Greater Taipei sits at **1.7–2.3%**, i.e. **43–60 years of rent**
to recoup the price. Type-splitting also reveals a non-obvious contrast: Taipei *towers* have a
*lower* PRR than walk-ups (new towers command strong rents), while New Taipei *towers* carry the
*highest* PRR.

### 3.3 Finding 2 — prices are near historical highs

Including 115S1, the latest-quarter median is **86.9 萬/坪 (Taipei)** and **51.0 萬/坪 (New Taipei)**,
both the **highest in the 4-year window** and above **94%** of all quarters.

### 3.4 Finding 3 — rent-vs-price divergence is detectable per area

For each (district × type) we track PRR over time. Example — **Zhonghe towers (中和大樓)**: PRR rose
to **70 (114S1)** then fell to **57 (115S1)** as price dropped ~11% YoY while rent rose ~10%. This
is exactly the "price decoupled from rent, then loosens" signal the product surfaces.

### 3.5 Willingness to pay

- **Agents (B2B):** comparable market-intelligence products (e.g. 實價登錄 Pro, 樂居) charge monthly
  subscriptions; a credibility/closing tool justifies a per-seat fee. The value is faster closes and
  fewer price disputes.
- **Buyers (B2C):** value is framed non-monetarily — avoiding overpaying on a multi-million-NTD
  purchase, and saving the hours currently spent manually cross-checking LVR. Monetised indirectly
  (lead-gen, freemium) plus a voluntary donation channel (Buy Me a Coffee).

> **Honest status.** Quantitative public-data evidence is complete. User interviews and a formal
> competitor-pricing table are listed as next steps (§8); the methodology to run them is in
> [`analysis/survey/`](analysis/survey/).

---

## 4. System Design (Required Component — technical)

### 4.1 Architecture (Lambda)

```
 Data sources            Ingestion          Processing                 Serving            Delivery
┌──────────────┐      ┌────────────┐   ┌────────────────────┐    ┌──────────────┐   ┌──────────────┐
│ LVR sale (a) │      │ scrapers   │   │ Batch layer        │    │ PostgreSQL   │   │ Streamlit    │
│ LVR rent (c) │─────▶│  → Kafka   │──▶│  PRR / percentile  │───▶│ (history)    │──▶│ dashboard    │
│ (雙北,17季)  │      │ (msg queue)│   │  trend / screen    │    │ Redis (hot)  │   │ REST/report  │
└──────────────┘      └────────────┘   │ Speed layer        │    │ MinIO (raw)  │   │ fair-price   │
   UI "refresh" ──────────┘            │  event alerts (P2) │    └──────────────┘   └──────────────┘
                                       └────────────────────┘
```

| Layer | Production tool (course paradigm) | Why |
|---|---|---|
| Message queue | **Kafka** | decouple scrapers from processing; replayable, scalable ingestion |
| Batch layer | **Spark (batch)** | recompute PRR / historical percentiles / trend over the full history |
| Speed layer | **Spark Structured Streaming** | low-latency policy/price-event alerts (Phase 2) |
| Hot store | **Redis** | instant lookup of latest per-district state |
| Cold store | **PostgreSQL** | structured historical transactions / indicators (SQL) |
| Raw lake | **MinIO** (S3-compatible) | original seasonal CSVs / snapshots |
| Delivery | **Streamlit** + exportable HTML report | dashboard, calculators, report |

### 4.2 Implemented prototype vs production design (full disclosure)

The submitted, runnable prototype is **single-node** to keep the demo reproducible: the *roles* of
Kafka/Spark/Redis/PostgreSQL/MinIO are played by a `pandas` + file-based pipeline and a Python
**subprocess job runner** ([`ingestion/pipeline.py`](ingestion/pipeline.py)) triggered by the UI's
"🔄 update" button (ingestion → processing → serving). The table above is the **scale-out mapping**:
because the workload is embarrassingly parallel by (district × type × quarter), the batch stage maps
directly onto Spark, the ingestion onto a Kafka topic, and the serving CSVs onto Redis/PostgreSQL.

### 4.3 Data sources, delivery, scalability

- **Sources:** LVR sale + rent (primary, legal). 591 / 樂居 considered only as optional, rate-limited
  research scrapers — **not** wired to the public UI button, due to ToS (see §6).
- **Delivery:** an interactive Streamlit dashboard, a downloadable one-page **fair-price report**
  (HTML, print-to-PDF), and the underlying summary CSVs as a data feed.
- **Scalability/cost:** data volume (~10⁵ rows/quarter for 雙北) is trivial for a single node;
  national coverage (~22 cities) or per-listing streaming is the 10–100× case that justifies the
  Kafka+Spark design. Deployment targets scale-to-zero (Cloud Run) to minimise cost (§7).

---

## 5. Product Features

1. **🌡️ PRR temperature** by city → district → **building type**, vs the same-type cross-region median.
2. **📐 Rent-vs-price divergence**: dual-axis price/rent time series + PRR-vs-own-history, with an
   automatic reading (e.g. "rent weakening but price sticky → likely to loosen").
3. **🚦 Entry-timing light**: combines valuation (PRR) × momentum (6-month price change) into a
   red/amber/green call with one-line advice.
4. **🏷️ "Where not to overpay"**: screens districts that are *cooling* (negative momentum) and
   *relatively cheap* (PRR below the same-type median).
5. **🔍 Comparable pricing**: enter price + size, filter comps by **size range** and **period
   (last 2y / prior 2y / all)**; shows percentile, negotiation band (P25–P75), histogram, and the
   most recent comparable sales **with addresses**.
6. **💰 Multi-product loan calculator**: 新青安 / standard first-home / second-home (credit-controlled
   60% LTV) / personal loan; with the **新青安 payment-cliff** simulation — the 5-year grace period
   raises the monthly payment ~**×2.8** (14,792 → 41,299 on a NT$10M loan).
7. **🔄 Affordability reverse-calc**: income × debt ratio + down payment → affordable total price and
   which districts are within reach (e.g. NT$100k/month → ~NT$12.2M).
8. **🧭 Policy & risk signals**: 新青安 demand-pull, central-bank credit controls, "volume leads price,"
   and foreclosure/cliff risk.
9. **🗺️ Map** (pydeck + Carto street tiles): districts coloured by PRR *or* momentum, hover tooltips.
10. **📄 Fair-price one-page report**: exportable HTML for agents to show clients.

---

## 6. Go-to-Market Difficulties (Bonus)

- **Agent conflict of interest.** A tool that flags "expensive" can deter sales; only
  trust-differentiated agents adopt it. Mitigation: position as a *closing-acceleration* and
  *dispute-reduction* tool, not a "cheap-hunting" tool.
- **Data acquisition & legal.** LVR is free and legally re-publishable — a strong moat against the
  cost/risk of scraping. 591/樂居 carry ToS and anti-scraping risk, so they are excluded from the
  public pipeline. LVR addresses are already public, but we still respect PDPA by not enriching with
  personal data.
- **Rental data coverage.** Rental LVR only became broadly mandatory ~2024, so PRR time series start
  at 112S4; pre-2024 rent is sparse. Disclosed in-product and in the methodology.
- **Cold-start / two-sided dynamics.** Buyers attract agents and vice-versa; we bootstrap the buyer
  side with a free, shareable tool and the credibility badge.
- **Competition & moats.** Incumbents (591 實價, 樂居, 實價登錄 Pro, the government site) show prices;
  our moat is *interpretation* — rent-anchored valuation, divergence detection, timing light, and the
  agent-ready report — not raw data.
- **Unit economics.** Marginal cost per user ≈ 0 (open data + scale-to-zero hosting). Revenue:
  agent subscriptions + per-report fees + voluntary donations; profitable at a small number of paying
  agents.

---

## 7. Deployment (Bonus)

Streamlit is a stateful server, so it cannot run on Firebase Hosting (static only). The cost-saving
Google path is **Cloud Run** (containerised, scale-to-zero, free tier), optionally fronted by
Firebase Hosting; the zero-effort free path is **Streamlit Community Cloud**. A `Dockerfile`
(with `fonts-noto-cjk` for chart CJK rendering) and full instructions are in
[`DEPLOY.md`](DEPLOY.md). The live URL is on page 1.

---

## 8. Limitations & Future Work

- PRR series begin 112S4 due to rental-registration coverage.
- The system surfaces **transparent leading indicators**, not a price forecast; momentum can be noisy
  in small districts (mitigated by 2-quarter smoothing and minimum-sample thresholds).
- The distributed stack (Kafka/Spark/Redis/PostgreSQL/MinIO) is *designed and mapped* but the
  prototype runs single-node; wiring real Kafka+Spark is the next engineering step.
- Demand evidence to add: user interviews and a formal competitor-pricing table.

---

## 9. Reproducibility & Repository

```bash
pip install -r requirements.txt
python ingestion/scrapers/lvr_gov.py     # download 雙北 LVR (cached)
python analysis/prr_validation.py        # clean + PRR + per-type tables + sale_clean.csv
python analysis/trend_signals.py         # per-quarter panel + cooling/value screen
streamlit run delivery/dashboard/app.py  # dashboard
```

Repository layout: `ingestion/` (scrapers + pipeline), `analysis/` (validation, trend signals,
methodology README, outputs), `delivery/` (dashboard, loan calculator, districts), `data/`
(`raw/` gitignored, `processed/` shipped), `docs/`. See [`README.md`](README.md) and
[`analysis/README.md`](analysis/README.md).

---

## References / Data Sources

- Ministry of the Interior, **Actual Price Registration (實價登錄)** open data —
  `https://plvr.land.moi.gov.tw/DownloadSeason`
- Ministry of Finance / 八大行庫, **新青安 (New Youth Housing Loan)** program terms.
- Central Bank of the R.O.C., selective credit-control measures.
- Course materials: distributed file systems, batch/stream processing (Spark), message queues
  (Kafka), NoSQL/SQL stores (Redis/PostgreSQL).
- Open-source: Streamlit, pandas, NumPy, Matplotlib, pydeck (attributed; see `requirements.txt`).
```
