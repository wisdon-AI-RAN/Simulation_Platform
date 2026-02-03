# Simulation Platform

這個專案目前聚焦在「CityGML/OBJ ➜ USD 轉換服務」以及（可選的）單一對外 Port Gateway。

`AODT-Agent` 已拆成獨立 repo/服務（建議獨立部署在高算力機器）。

在「同機開發」情境下，你也可以用本 repo 的 dev compose 把 AODT-Agent 當作**可選的內部 service** 啟動（見下方 `docker-compose.dev.yml`）。

## 架構概覽

- **gml2usd**：提供 CityGML/OBJ ➜ USD 的 API，並可輸出 glTF（預設回傳 bundle zip：`.usd` + glTF 資產組）。
- **Gateway（可選）**：Nginx 以「單一對外 Port」做路徑轉發。
	- `/health`、`/process_gml`、`/process_obj`、`/list_files` ➜ gml2usd

## 快速啟動（建議：單一 Port 模式）

前置需求：Docker + Docker Compose

1) 準備環境變數

- 複製並調整 [gml2usd/.env.example](gml2usd/.env.example) ➜ `gml2usd/.env`

（可選）如需固定 Gateway 對外 Port：複製並調整 [.env.example](.env.example) ➜ `.env`

2) 啟動（在專案根目錄 `Simulation_platform/` 執行）

```bash
docker compose up -d --build
```

（可選）同機開發：啟動 AODT-Agent（需先把 AODT-Agent repo clone 到本 repo 的上一層資料夾，例如 `../AODT-Agent`）

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

預設對外 Port：`8082`（可用環境變數改成你要的 Port）

```bash
AODT_GATEWAY_PUBLIC_PORT=5000 docker compose up -d --build
```

## API

### gml2usd

gml2usd 的 API/參數與 curl 範例請看 [gml2usd/README.md](gml2usd/README.md)。

## 資料夾與檔案輸出

- [gml2usd/gml_original_file](gml2usd/gml_original_file)：原始 CityGML 資料（非常大，建議用 volume mount）
- [gml2usd/processed_gmls](gml2usd/processed_gmls)：中間產物/輸出 GML
- [gml2usd/processed_usds](gml2usd/processed_usds)：輸出 USD（API 回傳後依 `keep_files` 決定是否保留）
- [gml2usd/uploads](gml2usd/uploads)：上傳 OBJ 的暫存
- [gml2usd/logs](gml2usd/logs)：gml2usd API log

## 常見問題（Troubleshooting）

- gml2usd 轉換時間較長：Gateway 的 timeout 與 `client_max_body_size` 設定在 [Simulation_Agent/gateway/nginx.conf](Simulation_Agent/gateway/nginx.conf)。
- gml2usd container 依賴本專案內的 `local_pydeps/`（含 prebuilt libs）與 Ubuntu 22.04 系統套件（如 `libicu70`）；建議使用 Docker 跑，不建議直接在 host 裝。