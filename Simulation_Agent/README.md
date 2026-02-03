# Simulation_Agent

這個資料夾是「整合層」：把整個 `Simulation_platform/` 視為一個模擬平台，並用單一對外 Port 透過 Nginx 轉發到多個 container。

## 目的
- 對外只開一個 port（預設 `8082`）
- 由 gateway 轉發：
  - `/health`, `/process_gml`, `/to_usd`, `/process_obj`, `/list_files` → gml2usd

## 前置條件
- 準備 `gml2usd/.env`（可從 `gml2usd/.env.example` 複製）

## 啟動（從平台根目錄）
在 `Simulation_platform/` 根目錄：

```bash
docker compose up -d --build
```

如需改對外 port（gateway 對外的單一 port）：

```bash
AODT_GATEWAY_PUBLIC_PORT=5000 docker compose up -d --build
```

你也可以在平台根目錄建立 `.env`（可參考 `.env.example`）來固定設定 `AODT_GATEWAY_PUBLIC_PORT`。

## 備註：AODT-Agent
`AODT-Agent` 已拆為獨立服務（不由本 compose 管控）。

## 停止
```bash
docker compose down
```

## Gateway 設定
Nginx 設定檔在 `Simulation_Agent/gateway/nginx.conf`。
