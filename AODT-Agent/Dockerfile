FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 複製需求檔並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式
COPY . .

# 開放 5000 port
EXPOSE 5000

# 啟動 server
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app", "--access-logfile", "-", "--error-logfile", "-"]
