# gml2usd

提供 CityGML/OBJ ➜ USD 的 Flask API。主要用 Docker 方式部署，API 會以 **binary** 回傳 `.usd` 檔。

## 這個資料夾在做什麼（應用/流程）

gml2usd 提供兩種常用轉換流程：

- **經緯度 ➜ CityGML ➜ USD**：`POST /process_gml`
  - 先呼叫 [Main.py](Main.py)（互動式腳本，但 API 會用 stdin 自動餵參數）在 `processed_gmls/` 產生 GML。
  - 再呼叫 [local_citygml2usd.py](local_citygml2usd.py) 透過 `/opt/aodt_ui_gis/` 的轉換腳本把 GML 轉成 USD。
- **上傳檔案 ➜ USD**：
  - `POST /to_usd`：上傳 CityGML（GML）檔案轉 USD。
  - `POST /process_obj`：上傳 OBJ，先用 [obj_converter.py](obj_converter.py) 轉成 GML，再轉 USD。

實際 API 入口在 [gml_api_ssh.py](gml_api_ssh.py)，容器內用 gunicorn 啟動（見 [Dockerfile](Dockerfile)）。

> 注意：`local_pydeps/` 與 `aodt_ui_gis/` 內含 prebuilt/native 相依（`PYTHONPATH` / `LD_LIBRARY_PATH`），因此強烈建議用 Docker 部署。

## 推薦啟動方式（單一 Port Gateway）

如果你要「部署給使用者」並且只想對外開一個 Port，請直接用本 repo 的單一 Port 模式（Nginx gateway 會轉發路由）：

1. 準備環境變數

- 複製並調整 [../AODT-Agent/.env.example](../AODT-Agent/.env.example) ➜ `../AODT-Agent/.env`
- 複製並調整 [.env.example](.env.example) ➜ `.env`

2. 啟動（在 `AODT-Agent/` 目錄下）

```bash
docker compose -f docker-compose.single-port.yml up -d --build
```

Gateway 會提供：`/health`、`/process_gml`、`/to_usd`、`/process_obj`、`/list_files`。

## 只部署 gml2usd（不含 gateway）

此 repo 目前沒有單獨的 `docker-compose.yml`（以單一 Port 模式為主）。如要只跑 gml2usd，可用 `docker build/run`：

```bash
# 在 gml2usd/ 目錄
docker build -t gml2usd:local .

mkdir -p processed_gmls processed_usds uploads logs

docker run --rm -p 5001:5001 \
  -v "$PWD/.env:/app/.env:ro" \
  -v "$PWD/gml_original_file:/app/gml_original_file:ro" \
  -v "$PWD/processed_gmls:/app/processed_gmls" \
  -v "$PWD/processed_usds:/app/processed_usds" \
  -v "$PWD/uploads:/app/uploads" \
  -v "$PWD/logs:/app/logs" \
  gml2usd:local
```

## 在全新的電腦上設定 API 服務（資料與目錄準備）

1) 確保環境

- 安裝 Docker / Docker Compose
- 建議使用 Linux 主機（容器內會用到 prebuilt native libs；見 [Dockerfile](Dockerfile)）

2) 建立必要資料夾（在 `gml2usd/` 目錄下）

```bash
mkdir -p gml_original_file processed_gmls processed_usds uploads logs
```

3) 準備 CityGML 原始資料（很大）

本專案的資料集位置就是 `gml2usd/gml_original_file/`（也就是本目錄下的 `gml_original_file/`）。

>[!warning]
> 這份資料集可能接近 30GB，請先確認磁碟容量。

如果你要從另一台主機/舊專案目錄同步資料到本 repo（例如 ov6000 上舊路徑 `/home/alvin/Auto_transport/gml_origin_file`），可用類似：

```bash
rsync -av --progress alvin@ov6000:/home/alvin/Auto_transport/gml_origin_file/ ./gml_original_file/
```

4) 準備環境變數

- 複製 [.env.example](.env.example) ➜ `.env`

注意：目前 API 本身不強依賴 `.env` 內容，但單一 Port compose 會掛載它，保留檔案可避免部署時漏檔。

## API

基礎服務：預設容器內 listen `5001`。

### `GET /health`

回傳 JSON（健康檢查）。

### `POST /process_gml`

輸入經緯度與範圍，先用 [Main.py](Main.py) 生成 GML，接著轉 USD 並回傳 USD binary。

Request body（JSON）：

```json
{
  "project_id": "0",
  "lat": 22.82539,
  "lon": 120.40568,
  "margin": 50,
  "gml_name": "map_aodt_0.gml",
  "epsg_in": "3826",
  "epsg_out": "32654",
  "disable_interiors": false
}
```

`disable_interiors=true` 時，轉換指令會加上 `--disable_interiors`。

## Curl 範例

先決定你要打哪個 base URL：

- 單一 Port gateway（推薦，預設）：`http://localhost:8082`
- 只跑 gml2usd（直接打 service port）：`http://localhost:5001`

以下以 `BASE_URL` 示範：

```bash
BASE_URL=http://localhost:8082
```

### 健康檢查

```bash
curl -sS "$BASE_URL/health"
```

### 用經緯度生成 USD（`/process_gml`）

```bash
curl -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"0","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","disable_interiors":false}' \
  -o map_aodt_0.usd
```

### 上傳 GML 轉 USD（`/to_usd`）

```bash
curl -sS -X POST "$BASE_URL/to_usd" \
  -F project_id=0 \
  -F epsg_in=3826 \
  -F epsg_out=32654 \
  -F disable_interiors=0 \
  -F gml_file=@./your.gml \
  -o map_aodt_0.usd
```

### 上傳 OBJ 轉 USD（`/process_obj`）

```bash
curl -sS -X POST "$BASE_URL/process_obj" \
  -F project_id=obj_demo \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F epsg_gml=3826 \
  -F epsg_usd=32654 \
  -F disable_interiors=0 \
  -F script_name=citygml2aodt_indoor_groundplane_domain.py \
  -F obj_file=@./your.obj \
  -o obj_demo.usd
```

如果你要在轉換前先驗證 OBJ 內容（例如必須包含 `floor` 與 `roof` 兩個 object/group 名稱），可加：

```bash
curl -sS -X POST "$BASE_URL/process_obj" \
  -F project_id=obj_demo \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F obj_file=@./your.obj \
  -F required_objects=floor,roof \
  -o obj_demo.usd
```

也可以跳過這個檢查（不建議，除非你的 OBJ 沒有 floor/roof 的命名慣例）：

```bash
curl -sS -X POST "$BASE_URL/process_obj" \
  -F project_id=obj_demo \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F obj_file=@./your.obj \
  -F skip_obj_validation=1 \
  -o obj_demo.usd
```

> 注意：上傳檔案一定要用 `@`（例如 `-F obj_file=@./your.obj`），否則後端會回 `No obj_file part`。

> 小提醒：如果你用 `-sS`（silent）加上 `-o out.usd`（寫檔），終端機本來就不會顯示任何回應內容；
> 若後端回 `400` JSON 錯誤訊息，也會被寫進 `.usd` 檔案。
> 建議加 `-f`（400/500 直接視為失敗）或加 `-w 'http=%{http_code}\n'` 印出狀態碼。

### 列出已產生的 GML（`/list_files`）

```bash
curl -sS "$BASE_URL/list_files"
```

### `POST /to_usd`

上傳 GML 檔案轉 USD（回傳 USD binary）。

multipart/form-data：

- `project_id`（必填）
- `epsg_in`（必填，常用 `3826`）
- `gml_file`（必填）
- `epsg_out`（選填，預設 `32654`）
- `disable_interiors`（選填，`1/true/yes` 會加上 `--disable_interiors`）

### `POST /process_obj`

上傳 OBJ 檔案，會先轉成 GML 再轉 USD（預設回傳 USD；也可回傳中間 GML）。

multipart/form-data：

- `obj_file`（必填）
- `lat`、`lon`（必填，WGS84，作為模型原點）
- `output`（選填：`usd` 或 `gml`，預設 `usd`）
- `keep_files`（選填：`1` 保留暫存檔；預設會清掉）
- `epsg_gml`（選填，預設 `3826`）
- `epsg_usd`（選填，預設 `32654`）
- `disable_interiors`（選填，`1/true/yes` 會加上 `--disable_interiors`）
- `script_name`（選填，指定 `/opt/aodt_ui_gis/` 的轉換腳本；預設 `citygml2aodt_indoor_groundplane_domain.py`）
- `required_objects`（選填，逗號分隔，例如 `floor,roof`；用來在轉換前驗證 OBJ 必須包含這些 object/group 名稱）
- `required_object`（選填，可重複多次；效果同 `required_objects`）
- `skip_obj_validation`（選填，`1/true/yes` 會跳過 OBJ 名稱檢查）

> 預設情況下（不指定 `required_objects`/`required_object` 且不設 `skip_obj_validation`），服務會要求 OBJ 內必須存在 `floor` 與 `roof`。
> 這通常來自 OBJ 中的物件/群組宣告行：`o floor`、`o roof`（或 `g floor`、`g roof`）。

### `GET /list_files`

列出 `processed_gmls/` 下的 `.gml` 檔案資訊。

## Notes / Troubleshooting

- 轉換工作可能很久：單一 Port 模式已在 [../AODT-Agent/gateway/nginx.conf](../AODT-Agent/gateway/nginx.conf) 放寬 `client_max_body_size` 與 timeout。
- gml2usd 使用 `local_pydeps/` 的 prebuilt 套件與 shared libs（見 [Dockerfile](Dockerfile) 的 `PYTHONPATH` / `LD_LIBRARY_PATH`），建議用 Docker 方式部署。
