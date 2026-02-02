# AODT-Agent

AODT Server 目前跑在 ov6000 上的 port 5000

## Docker

在建立環境之前，記得先將 `.env.example` 複製一份，並命名為 `.env`，並修改裡面的環境變數，變數敘述可看 `.env.example` 裡面的註解

Build docker image
```bash
 docker compose -p aodt-server up -d --build
```

## 單一 Port（同時提供 AODT-Agent + gml2usd）

這個模式會額外啟動一個 Nginx gateway，對外只開一個 port，並把：
- `/restart`、`/test` 轉發到 AODT-Agent
- `/process_gml`、`/to_usd`、`/health` 轉發到 gml2usd

前置條件：
- 請先準備好 `../gml2usd/.env`（可參考 `../gml2usd/.env.example`）

啟動：
```bash
docker compose -f docker-compose.single-port.yml up -d --build
```

對外 port 預設是 `8082`，可用環境變數調整：
```bash
AODT_GATEWAY_PUBLIC_PORT=5000 docker compose -f docker-compose.single-port.yml up -d --build
```