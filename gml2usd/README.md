# 生成CITYGML，USD的相關腳本

## 快速啟動5G-ORAN需要的轉換API服務
### 啟動設定好、現有的API服務
- 先SSH以alvin進入伍老師實驗室裡的ov6000
- 進入遠端後，輸入以下指令，就啟動了
  ```bash
  cd Auto_transport
  docker compose up --build
  ```
- 關閉API服務
  ```bash
  docker compose down
  ```

### 在全新的電腦上設定API服務
- 先確保這台電腦上有SSH server與docker
- 建立一個user，需要有sudo和docker權限，在Ubuntu上你可以把這個user加入sudo與docker群組。
- 在clone下來後的資料夾下建立三個資料夾:processed_gmls、processed_usds、gml_original_file
- 將GML檔案從alvin@ov6000複製到剛剛創建的gml_original_file資料夾下。GML檔案在alvin@ov6000的路徑為`/home/alvin/Auto_transport/gml_origin_file`。
>[!warning]
> 這個檔案大小接近30GB，請斟酌你的磁碟大小
- 複製.env example，改名為.env。
- 將先前提到的user和機器的資訊填入.env中
- 啟動docker compose:
```bash
docker compose up --build
```

## 有提供的API服務
#### 健康檢查
- **URL**: `/health`
- **方法**: `GET`
- **返回範例**
  ```json
  {
    "status": "healthy",
    "version": "1.0",
    "timestamp": "2023-09-01T12:34:56.789012"
  }
  ```

#### 用經緯度生成GML與USD檔，並回傳USD
- **URL**: `/process_gml`
- **方法**: `POST`
- **使用方式**:使用時可以只填lat,lon,margin
  ```json
  {
    "lat": 22.82539,
    "lon": 120.40568,
    "margin": 50,
    "gml_name": "map.gml",
    "container_id": "backend_gis_1",
    "epsg_in": "3826",
    "epsg_out": "32654"
  }
  ```
- **返回內容**
  - 200:會回傳一個USD的binary檔案
  - 400,404,500:
    ```json
    {
      "status": "error",
      "message": "...",
      "details": "..."
    }
    ```

#### 提供GML，回傳USD
- **URL**: `/to_usd`
- **方法**: `POST`
- **使用方式**: 
  - 使用Form-data的格式傳出去，會帶有三個欄位:
  - espg_in:使用預設的epsg_in(3826)即可
  - project_id:這個project的id
  - gml_file: 要被轉換的gml檔案
  - epsg_out:使用預設32654即可
- **返回內容**
  - 200:會回傳一個USD的binary檔案
  - 400,404,500:
    ```json
    {
      "status": "error",
      "message": "...",
      "details": "..."
    }
    ```

#### 提供GML，回傳USD
- **URL**: `/list_files`
- **方法**: `GET`
- **返回內容**
  ```json
  {
    "status": "success",
    "count": 2,
    "files": [
      {
        "name": "Tianliao.gml",
        "path": "processed_gmls/Tianliao.gml",
        "size": 12345,
        "created": "2023-09-01T12:34:56.789012"
      },
      {
        "name": "Tainan.gml",
        "path": "processed_gmls/Tainan.gml",
        "size": 67890,
        "created": "2023-09-02T10:11:12.131415"
      }
    ]
  }
  ```


## 介紹
- 這個repo中有三種提供服務的方式
- 第一種為本機架設API服務
- 第二種為docker架設API服務(最新，5G-ORAN使用)
- 第三種為本機輸入指令操作 

## gml_origin_file與gml_bounding_boxes_v1.csv資訊

### gml_origin_file
- gml_origin_file底下有三個資料夾，分別代表三個縣市中的建築物:高雄、新竹、新北市
- 資料是以CITYGML的形式呈現，這種檔案與一般GML不同在於它是特別針對城市景觀設計的檔案。包含一些城市中常見的物件的模板(如:馬路，建物)，與他們的外表樣式。
- 在ada6000上的檔案只有建築物

### gml_boundgin_boxes_v1.csv
- 這個檔案中有所有在gml_origin_file中，GML檔案的bounding box(也就是這個檔案的邊界)
- 每個row有三個資訊Filename,LowerCorner(邊界最小值),UpperCorner(邊界最大值)
- 感覺是可以加速合併GML的速度，不需要打開每一個gml_origin_file去看他的座標
- 使用create_gml_index.py生成:生成方法
  1. 進入這個腳本，把directories改成gml檔案存放的地方
  2. 把output_csv改成想要的名稱
  3. run script


## 方法一:本機架設API服務
- 本機架設API服務的意思，意思是這個API服務可以直接通過bash，去呼叫本地的docker，讓他去執行某些命令。
- 這個方法需要的檔案有:
  - manage_api_service.sh: 管理API服務
  - remote_auto_gml_processing.py: 負責控制生成GML與轉換USD的流程
  - gml_api.py: API服務腳本
  - Main.py: 負責生成GML
  - gml_bounding_boxes_v1.csv: 包含所有CITYGML文件的bounding_box，用於查詢該文件是否在範圍內
  - gml_transport_v2:　不知道幹嘛用的
  - gml_original_file/.: gml原始檔案
  - requirements.txt: 依賴的python package
  - backend_gis_1這個容器: 將GML轉換成USD的工具
### 啟動方式
- 先SSH以alvin進入伍老師實驗室裡的ov6000
- 進入Auto_transport，輸入以下指令，就啟動了
  ```bash
  ./manage_api_service.sh start
  ```
- 需要查看是否正常啟動時，輸入
  ```bash
  ./manage_api_service.sh status
  ```
- 需要關閉服務時
  ```bash
  ./manage_api_service.sh stop
  ```
- 重新啟動服務
  ```bash
  ./manage_api_service.sh restart
  ```
### 腳本細節
- Main.py:吃經緯度與範圍，將GML生成出來。
  - 由內政部提供的GML檔案，原先是一棟一棟、分開在不同檔案存的
  - Main.py的功能就是將在範圍內的建物GML檔案，合成成為一份GML檔
  - 合併的過程大致如下，細節可以去問子豪學長:
    1. 先使用gml_bounding_boxes_v1.csv篩選出bounding box與指定範圍有重疊到的GML檔案。
    2. 再將篩選出的檔案一個一個打開，檢查在範圍內的建築物，將所有合法的建築物整合成一個list。
    3. 再將檔案依次打開
    4. 依照這個list，將需要的檔案打開並提取出建築物，生成一個temp_output.gml
    5. 將這個temp_output.gml合成進最後要輸出的檔案。
    6. 重複步驟3~5直到整個list都完成
- remote_auto_gml_processing.py:吃經緯度與範圍，將GML與USD生成出來。
  - 總共有五個步驟
    1. 呼叫Main.py，生成GML檔並且存在./processed_gmls
    2. 使用docker cp backend_gis_1 ... ，將檔案複製進容器內部
    3. 使用docker exec python3 /src/aodt_gis/aodt_py/aodt_ui_gis/gis_jobs/gml_job.py ... 進行GML轉USD
    4. 使用docker cp ./processed_gmls backend_gis_1 ... 將USD從容器中取出
    5. 使用docker exec rm ... 刪除容器內的USD與GML，避免檔案堆積
  - 這個檔案有另一個附加函數gml2usd，只有運行上述2~5步
  - 這個檔案主要是不斷使用command line去呼叫Main.py與docker。(這也是主機架設較簡單的原因)
  
- gml_api.py: 使用flask製作的接收API端點
  - 預設gml與usd的存放位置
  - 預設gml與usd的檔案名稱
  - 將請求的資料與檔案位置餵給remote_auto_gml_processing.py
  - 回傳檔案與清空資料夾

- manage_api_service.sh: 管理API的啟動、關閉與重開
  - 是一個shell script
  - 會檢查並設定虛擬環境、檢查輸出目錄存在、啟動gunicorn(這個是HTTP伺服器)、設定logfile位置等
- 因為有shell scrtpt，所以應該只能用在linux?


## 方法二: docker架設API服務
- 這個方法與上一個方法幾乎相同，只是由於某些原因，我們將生成gml的程式與API的腳本放進容器中。
- 這個方案需要的檔案有:
  - Dockerfile與 docker-compose.yml:建立容器用
  - remote_auto_gml_processing_ssh.py: 負責控制生成GML與轉換USD的流程
  - gml_api_ssh.py: API服務腳本
  - Main.py: 負責生成GML
  - gml_bounding_boxes_v1.csv: Main.py需要的gml相關資料
  - gml_transport_v2:　不知道幹嘛用的
  - gml_original_file/.: gml原始檔案
  - requirements.txt: 依賴的python package
  - backend_gis_1這個容器: 將GML轉換成USD的工具

### 啟動方式
>與[快速啟動5G-ORAN需要的轉換API服務](#快速啟動5G-ORAN需要的轉換API服務)啟動的方法相同

### 腳本細節
- 由於API被容器裝起來，與本地隔離開了。檔案的交換與下指令與上個方法不同。
- remote_auto_gml_processing_ssh.py: 用ssh的方式連回本機下指令。
  - 使用paramiko這個python套件來下指令
  - 檔案儲存的位置分成在容器內與在本地，容器內檔案會存在/app/processed_gmls與/app/processed_usds，並且會被mount到 ${SSH_HOST_DIR}/processed_gmls與${SSH_HOST_DIR}/processed_usds中
- gml_api_ssh.py: 與gml_api.py幾乎相同，只差在呼叫的是remote_auto_gml_processing_ssh.py
- Dockerfile:建立容器設定
  - 依照這個檔案建立轉換容器
  - 如果想要新增檔案進容器、更改容器接口、或是更改初始運行指令內容(workers,timeout,apifile)都在這裡修改
- docker-compose.yml:執行容器設定
  - 可以更改執行容器時的設定
  - 包括但不限於:dockerfile名字、mount在容器中/主機的位置、對外的port等等
- .env: 環境變數存放處
  - 本機ip、本機port、username、password、host directory




## 方法三: 本機輸入指令操作
- 先SSH以alvin進入伍老師實驗室裡的ov6000
- 進入Auto_transport，輸入以下指令
  ```bash
  ./Auto_gml_process.sh
  ```
- 這行指令會運行這個shell script，接著依照提示，依序輸入緯度、經度、半徑與文件名，腳本就會自動進行轉換。
- 生成的GML會在/processed_gmls下，生成的USD則是會留一份在backend_gis_1中/src/aodt_gis/data/usd_file/，另一份則是會放入omniverse://omniverse-server/Users/aerial/osm/底下
- 腳本會幫忙建立python的虛擬環境與下載需要的package
- 這個方法，依賴的檔案有:
  - Auto_gml_process.sh:　管理環境，接收使用者輸入
  - auto_gml_processing.py: 負責控制生成GML與轉換USD的流程
  - Main.py: 負責生成GML
  - gml_bounding_boxes_v1.csv: Main.py需要的gml相關資料
  - gml_transport_v2:　不知道幹嘛用的
  - gml_original_file/.: gml原始檔案
  - requirements.txt: 依賴的python package
  - backend_gis_1這個容器: 將GML轉換成USD的工具


### 轉換流程
>由於我沒有細究Main.py，因此轉換過程我不熟悉。
1. 當呼叫Auto_gml_processing.sh時，會先建立虛擬環境與下載package。
2. 接下來會呼叫auto_gml_processing.py。
3. auto_gml_processing.py會先呼叫Main.py，將GML檔案生成出來。
4. 接著會把GML檔案放入backend_gis_1容器中。
5. 由容器將檔案轉換成USD檔後，一份放在容器中，另一份放入AODT後端
6. 如果想要USD檔案，請使用docker cp backend_gis_1:/src/aodt_gis/data/usd_file/{base_name}.usd /path/to/folder，將檔案給複製出來
