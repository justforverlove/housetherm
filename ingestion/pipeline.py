"""
pipeline.py — UI 觸發的資料更新流程（合法來源：內政部實價登錄）

單機示範版：ingestion → processing → serving 三階段。
生產環境對應（見 README 架構）：
  UI 事件 → Kafka topic(message queue) → Spark batch 清理/計算 → DB(serving)

注意：本流程只更新「實價登錄」（政府開放資料）。591/樂居因 ToS 與反爬蟲，
不在公開按鈕觸發範圍，僅作限速研究爬蟲，相關風險見報告 Go-to-Market 章節。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args, log):
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-600:])


def refresh(log=print):
    """執行一次完整資料更新；log 為接收進度訊息的 callable。"""
    log("① ingestion：下載/更新實價登錄（雙北，含快取，未釋出季別自動略過）…")
    _run([sys.executable, str(ROOT / "ingestion" / "scrapers" / "lvr_gov.py")], log)
    log("② processing：清理（分房型/排除車位/踢非市場交易）+ 計算 PRR + 匯出明細 …")
    _run([sys.executable, str(ROOT / "analysis" / "prr_validation.py")], log)
    log("③ processing：逐季走勢 + 區域降溫/便宜訊號 …")
    _run([sys.executable, str(ROOT / "analysis" / "trend_signals.py")], log)
    log("④ serving：彙整表、成交明細、走勢訊號已更新，dashboard 即將重新載入。")
