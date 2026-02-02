import pandas as pd
import pyproj
import os

def parse_coords(coord_str):
    """ 將 'x y' 字串解析為 (x, y) tuple """
    try:
        parts = coord_str.strip().split()
        return float(parts[0]), float(parts[1])
    except:
        return None, None

def wgs84_to_epsg3826(lat, lon):
    """ 將 WGS84 經緯度轉為 EPSG:3826 坐標 (公尺) """
    src_crs = pyproj.CRS("EPSG:4326")
    tgt_crs = pyproj.CRS("EPSG:3826")
    transformer = pyproj.Transformer.from_crs(src_crs, tgt_crs, always_xy=True)
    return transformer.transform(lon, lat)

def find_overlapping_files(csv_path, lat, lon, margin_m, output_txt="matched_gml_files.txt"):
    # 轉換輸入點到 EPSG:3826
    x_center, y_center = wgs84_to_epsg3826(lat, lon)

    # 定義查詢範圍
    x_min = x_center - margin_m
    x_max = x_center + margin_m
    y_min = y_center - margin_m
    y_max = y_center + margin_m

    # 載入 CSV
    if not os.path.exists(csv_path):
        print(f"找不到 CSV 檔案: {csv_path}")
        return

    df = pd.read_csv(csv_path)

    # 解析 lower/upper corner
    df[['lower_x', 'lower_y']] = df['LowerCorner'].apply(lambda s: pd.Series(parse_coords(str(s))))
    df[['upper_x', 'upper_y']] = df['UpperCorner'].apply(lambda s: pd.Series(parse_coords(str(s))))

    # 篩選與查詢範圍有交集的
    overlap = df[
        (df['upper_x'] >= x_min) &
        (df['lower_x'] <= x_max) &
        (df['upper_y'] >= y_min) &
        (df['lower_y'] <= y_max)
    ]

    matched_filenames = overlap['Filename'].dropna().unique()

    # 輸出結果到 txt 檔
    with open(output_txt, "w", encoding="utf-8") as f:
        for name in matched_filenames:
            f.write(f"{name}\n")

    print(f"找到 {len(matched_filenames)} 筆匹配的 GML，已寫入 {output_txt}")

# ===== 主程式 =====
if __name__ == "__main__":
    # 使用者輸入
    lat = float(input("請輸入緯度 (例如 24.786991): "))
    lon = float(input("請輸入經度 (例如 120.996659): "))
    margin_m = float(input("請輸入匡列範圍半徑 margin_m（單位：公尺，例如 2000）: "))

    # CSV 檔路徑（假設和程式在同個資料夾）
    csv_file_path = "gml_bounding_boxes_v1.csv"

    # 執行查詢
    find_overlapping_files(csv_file_path, lat, lon, margin_m)
