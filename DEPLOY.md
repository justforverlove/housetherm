# 部署指南 (Deployment)

> ⚠️ **為什麼不是純 Firebase Hosting？** Firebase Hosting 只服務「靜態檔案」(HTML/CSS/JS)，
> 而 Streamlit 是常駐的 Python 伺服器（WebSocket）。在 Google 體系要跑 Streamlit、又要省錢，
> 正解是 **Cloud Run**（容器、可縮到零、有免費額度）；Firebase Hosting 可選擇性當作前端代理。
> 若只想「免費又最省事」，用 **Streamlit Community Cloud** 即可。

---

## 方案 A：Cloud Run（GCP，推薦給「想放 Firebase/Google、省錢」）

Cloud Run 會在沒有流量時縮放到 0，幾乎不收費；有免費額度。

```bash
# 0. 前置：安裝 gcloud、登入、設定專案
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# 1. 由原始碼直接建置並部署（用本專案 Dockerfile）
gcloud run deploy housetherm \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8080

# 部署完成會回傳一個 https URL，貼到報告第一頁即可。
```

### （可選）用 Firebase Hosting 當前端、轉址到 Cloud Run
若想要 firebase 網域 / CDN，在 `firebase.json` 設定 rewrite：

```jsonc
{
  "hosting": {
    "public": "public",
    "rewrites": [
      { "source": "**", "run": { "serviceId": "housetherm", "region": "asia-east1" } }
    ]
  }
}
```
```bash
firebase deploy --only hosting
```

---

## 方案 B：Streamlit Community Cloud（最簡單、完全免費）

1. 把整個 repo 推到 GitHub（含 `requirements.txt`、`data/processed/sale_clean.csv`、`analysis/outputs/*.csv`）。
2. 到 https://share.streamlit.io → New app → 選 repo → 主檔填 `delivery/dashboard/app.py`。
3. Deploy，得到 `https://<app>.streamlit.app` URL，貼到報告第一頁。

---

## 部署需要哪些檔案在 repo 內？

App 啟動時讀取（**非** `data/raw/`，那是原始大檔，不需上傳）：
- `analysis/outputs/prr_by_district.csv`、`prr_by_city.csv`、`price_trend_by_season.csv`、`value_screen.csv`、`trend_panel.csv`
- `data/processed/sale_clean.csv`

這些由 `python analysis/prr_validation.py && python analysis/trend_signals.py` 產生；
請確保它們已 commit（`.gitignore` 只忽略 `data/raw/`，這些會保留）。

## 上線前小提醒
- 把 `delivery/dashboard/app.py` 底部 Buy Me a Coffee 連結的 `YOUR_USERNAME` 換成你的帳號。
- 「🔄 更新實價登錄資料」按鈕在雲端會即時下載政府開放資料並重算；首次可能較久，記憶體建議 ≥1Gi。
