# 房價溫度計 HouseTherm — 容器化（適用 Cloud Run / 任何容器平台）
FROM python:3.11-slim

# 中文字型（matplotlib 圖表用），避免容器內中文變成方框
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run 會以環境變數 PORT 指定埠（預設 8080）
ENV PORT=8080
EXPOSE 8080

CMD streamlit run delivery/dashboard/app.py \
    --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true
