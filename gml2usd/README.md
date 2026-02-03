# gml2usd

提供 CityGML/OBJ ➜ USD 的 Flask API。主要用 Docker 方式部署，API 會以 **binary** 回傳 `.usd` 檔。

## 這個資料夾在做什麼（應用/流程）

gml2usd 提供兩種常用轉換流程：

- **經緯度 ➜ CityGML ➜ USD**：`POST /process_gml`
  - 先呼叫 [Main.py](Main.py)（互動式腳本，但 API 會用 stdin 自動餵參數）在 `processed_gmls/` 產生 GML。
  - 再呼叫 [local_citygml2usd.py](local_citygml2usd.py) 透過 `/opt/aodt_ui_gis/` 的轉換腳本把 GML 轉成 USD。
- **上傳檔案 ➜ USD**：
  - `POST /process_obj`：上傳 OBJ，先用 [obj_converter.py](obj_converter.py) 轉成 GML，再轉 USD。

實際 API 入口在 [gml_api_ssh.py](gml_api_ssh.py)，容器內用 gunicorn 啟動（見 [Dockerfile](Dockerfile)）。

> 注意：`local_pydeps/` 與 `aodt_ui_gis/` 內含 prebuilt/native 相依（`PYTHONPATH` / `LD_LIBRARY_PATH`），因此強烈建議用 Docker 部署。

## 推薦啟動方式（單一 Port Gateway）

如果你要「部署給使用者」並且只想對外開一個 Port，請使用本平台根目錄的 Gateway（Nginx 會轉發路由）：

1. 準備環境變數

- 複製並調整 [.env.example](.env.example) ➜ `.env`

2. 啟動（在平台根目錄 `Simulation_platform/`）

```bash
docker compose up -d --build
```

Gateway 會提供：`/health`、`/process_gml`、`/process_obj`、`/list_files`。

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

輸入經緯度與範圍，先用 [Main.py](Main.py) 生成 GML，接著轉 USD。

> 預設（不指定 `output`）會回傳 `zip bundle`：`.usd` + glTF 資產組（通常是 `.gltf` + `.bin`；若有貼圖也會一起打包）。
> 若指定 `"output":"usd"`，則只回傳 `.usd`。

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
  "disable_interiors": false,
  "keep_files": false
}
```

`disable_interiors=true` 時，轉換指令會加上 `--disable_interiors`。

`keep_files=true` 時，服務端會保留 `processed_gmls/*.gml` 與 `processed_usds/*.usd`（方便你之後用 `GET /list_files` 檢查或到 volume 目錄查看）。

## Curl 範例

先決定你要打哪個 base URL：

- 單一 Port gateway（推薦，預設）：`http://localhost:8082`
- 只跑 gml2usd（直接打 service port）：`http://localhost:5001`


## 使用範例

這裡的目標是：

- **統一輸出檔名**（不同流程都用同一個 `NAME`）
- **OBJ 先驗證必要建築物名稱**（例如 `floor`、`roof`），避免轉出來才發現缺物件

> 註：bundle（`.usd` + glTF 資產組）的回傳方式是 API 的預設行為；目前不提供一個顯式的 `output=bundle` 參數。
- 預設 bundle zip 可以確保「同一次轉換」產出的 USD 與 glTF 是一致的一組結果，對使用者/前端下載保存也最簡單。

> 小提醒：`curl -o 檔名` 只是在你本機存檔的檔名，**不會**改變後端回傳的格式；要改回傳格式請用 `output` 參數。


### 基礎：OBJ ➜ bundle（統一檔名 + 必要物件驗證）
#### 根據不同project可能會修改參數 : NAME , lat , lon 

```bash
NAME=Askey
BASE_URL=http://localhost:8082

curl -f -sS -X POST "$BASE_URL/process_obj" \
  -F project_id="$NAME" \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F epsg_gml=3826 \
  -F epsg_usd=32654 \
  -F disable_interiors=1 \
  -F script_name=citygml2aodt_indoor_groundplane_domain.py \
  -F obj_file=@./"$NAME".obj \
  -F output_basename="$NAME" \
  -F required_objects=floor,roof \
  -F skip_obj_validation=0 \
  -o "$NAME".zip
```

### OBJ 只輸出 USD

```bash
NAME=Askey
BASE_URL=http://localhost:8082

curl -f -sS -X POST "$BASE_URL/process_obj" \
  -F project_id="$NAME" \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F epsg_gml=3826 \
  -F epsg_usd=32654 \
  -F disable_interiors=1 \
  -F script_name=citygml2aodt_indoor_groundplane_domain.py \
  -F obj_file=@./"$NAME".obj \
  -F output_basename="$NAME" \
  -F required_objects=floor,roof \
  -F skip_obj_validation=0 \
  -F output=usd \
  -o "$NAME".usd
```

### OBJ 只輸出 glTF

> 依你的需求（先忽略 `.bin`）：`output=gltf` 會回傳 **單一 `.gltf`**（服務端會把 `.bin/貼圖` 內嵌成 data URI）。
> 若你真的需要「傳統多檔 glTF」下載（`.gltf` + `.bin` + textures），可改用 `output=gltf_zip`（回傳 zip）。

```bash
NAME=Askey
BASE_URL=http://localhost:8082

# glTF (single .gltf)
curl -f -sS -X POST "$BASE_URL/process_obj" \
  -F project_id="$NAME" \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F epsg_gml=3826 \
  -F epsg_usd=32654 \
  -F disable_interiors=1 \
  -F script_name=citygml2aodt_indoor_groundplane_domain.py \
  -F obj_file=@./"$NAME".obj \
  -F output_basename="$NAME" \
  -F required_objects=floor,roof \
  -F skip_obj_validation=0 \
  -F output=gltf \
  -o "$NAME".gltf
```

### 基礎：經緯度 ➜ bundle（統一檔名）
#### 根據不同project可能會修改參數 : NAME , lat , lon , margin

```bash
NAME=Askey
BASE_URL=http://localhost:8082

curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"'"$NAME"'","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","gml_name":"'"$NAME"'.gml"}' \
  -o "$NAME".zip
```

### 經緯度只輸出 USD / glTF

```bash
NAME=Askey
BASE_URL=http://localhost:8082

# USD
curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"'"$NAME"'","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","disable_interiors":false,"output":"usd","gml_name":"'"$NAME"'.gml"}' \
  -o "$NAME".usd

# glTF (single .gltf)
curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"'"$NAME"'","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","disable_interiors":false,"output":"gltf","gml_name":"'"$NAME"'.gml"}' \
  -o "$NAME".gltf
```

### API狀態檢查

```bash
curl -sS "$BASE_URL/health"
```

## 額外參考（進階用法）
### 經緯度生成（`/process_gml`）
基礎範例（bundle zip）：

```bash
curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"0","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","disable_interiors":false,"gml_name":"map_aodt_0.gml"}' \
  -o map_aodt_0_bundle.zip
```
> （不指定 `output`）會回傳 `zip`，內含：`.usd` + **glTF 檔案組**（通常是 `.gltf` + `.bin`，若有貼圖也會一起打包）。
> 為什麼不是直接回傳 `.gltf`？因為 `.gltf` 常常不是單一檔案（會依賴 `.bin/貼圖`），HTTP 回應一次只能回傳一個檔案，所以預設用 zip 包起來。

額外：如果你只想拿 USD（不產生 glTF）：

```bash
curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"0","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654","disable_interiors":false,"output":"usd"}' \
  -o map_aodt_0.usd
```

### 上傳 OBJ（`/process_obj`）

基礎範例（bundle zip）：

```bash
curl -f -sS -X POST "$BASE_URL/process_obj" \
  -F project_id=obj_demo \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F epsg_gml=3826 \
  -F epsg_usd=32654 \
  -F disable_interiors=0 \
  -F script_name=citygml2aodt_indoor_groundplane_domain.py \
  -F obj_file=@./your.obj \
  -o obj_demo_bundle.zip
```

> 預設（不指定 `output`）會回傳 `zip`，內含：`.usd` + **glTF 檔案組**（通常是 `.gltf` + `.bin`，若有貼圖也會一起打包）。
> 如果你想要「單一檔案」比較好存取/下載，請用 `output=glb`。

> 檔名規則：zip 內檔案會預設以你上傳的 OBJ 檔名當 base name，例如上傳 `Askey.obj`，zip 內會是 `Askey.usd`、`Askey.gltf`、`Askey.bin`。
> 如需覆蓋檔名，可加 `-F output_basename=MyName`。

如果你只想拿 USD（不產生 glTF）：

```bash
curl -f -sS -X POST "$BASE_URL/process_obj" \
  -F project_id=obj_demo \
  -F lat=22.82539 \
  -F lon=120.40568 \
  -F obj_file=@./your.obj \
  -F output=usd \
  -o obj_demo.usd
```

額外：如果你要在轉換前先驗證 OBJ 內容（例如必須包含 `floor` 與 `roof` 兩個 object/group 名稱），可加：

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

### `POST /process_obj` API 內容格式

上傳 OBJ 檔案，會先轉成 GML 再轉 USD。

> 預設（不指定 `output`）會回傳 `zip bundle`：`.usd` + glTF 資產組。

multipart/form-data：

- `obj_file`（必填）
- `lat`、`lon`（必填，WGS84，作為模型原點）
- `output`（選填：`usd` / `gml` / `gltf` / `gltf_zip` / `glb`）
  - 不指定（預設）：回傳 bundle zip（`.usd` + glTF 資產組）
  - `usd`：只回傳 `.usd`
  - `gml`：只回傳中間產物 `.gml`
  - `gltf`：回傳單一 `.gltf`（服務端會把 `.bin/貼圖` 內嵌成 data URI）
  - `gltf_zip`：回傳傳統 glTF zip（`.gltf` + `.bin`，若有貼圖也會一起打包）
  - `glb`：回傳單一 `.glb`
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

- 轉換工作可能很久：單一 Port 模式已在 [../Simulation_Agent/gateway/nginx.conf](../Simulation_Agent/gateway/nginx.conf) 放寬 `client_max_body_size` 與 timeout。
- gml2usd 使用 `local_pydeps/` 的 prebuilt 套件與 shared libs（見 [Dockerfile](Dockerfile) 的 `PYTHONPATH` / `LD_LIBRARY_PATH`），建議用 Docker 方式部署。
