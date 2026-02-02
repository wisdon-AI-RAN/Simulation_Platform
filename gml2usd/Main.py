import xml.etree.ElementTree as ET
import pandas as pd
import pyproj
import os
import copy
import itertools
from pathlib import Path
from gml_transport_v2 import extract_buildings_from_gml  # 引入函數

def read_excluded_ids_from_file(filepath="excluded_buildings.txt"):
    """從配置文件中讀取要排除的建物ID"""
    excluded_ids = []
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳過空行和註釋行
                    if line and not line.startswith('#'):
                        excluded_ids.append(line)
            print(f"從 {filepath} 讀取到 {len(excluded_ids)} 個排除的建物ID")
        else:
            print(f"配置文件 {filepath} 不存在，將不排除任何建物")
    except Exception as e:
        print(f"讀取排除配置文件時出錯: {e}")
    
    return excluded_ids

def wgs84_to_epsg3826(lat, lon):
    """將 WGS84 經緯度轉為 EPSG:3826 坐標"""
    src_crs = pyproj.CRS("EPSG:4326")
    tgt_crs = pyproj.CRS("EPSG:3826")
    transformer = pyproj.Transformer.from_crs(src_crs, tgt_crs, always_xy=True)
    return transformer.transform(lon, lat)

def find_matching_gmls(csv_path, lat, lon, margin_m):
    """找到符合範圍的 GML 文件"""
    x_center, y_center = wgs84_to_epsg3826(lat, lon)
    
    # 定義查詢範圍
    x_min = x_center - margin_m
    x_max = x_center + margin_m
    y_min = y_center - margin_m
    y_max = y_center + margin_m
    
    # 載入 CSV
    df = pd.read_csv(csv_path)
    
    # 解析座標
    df[['lower_x', 'lower_y']] = df['LowerCorner'].str.extract('(\d+\.\d+)\s+(\d+\.\d+)').astype(float)
    df[['upper_x', 'upper_y']] = df['UpperCorner'].str.extract('(\d+\.\d+)\s+(\d+\.\d+)').astype(float)
    
    # 篩選符合範圍的文件
    matched = df[
        (df['upper_x'] >= x_min) &
        (df['lower_x'] <= x_max) &
        (df['upper_y'] >= y_min) &
        (df['lower_y'] <= y_max)
    ]
    
    # 構建可能的文件目錄
    # 有些資料集是把 .gml 直接放在資料夾底下（沒有 /gml 子資料夾），因此同時支援兩種結構：
    # - ./gml_original_file/<AREA>/gml/<file>.gml
    # - ./gml_original_file/<AREA>/<file>.gml
    base_dirs = [
        r"./gml_original_file/111_E_BUILD",
        r"./gml_original_file/111_F_BUILD",
        r"./gml_original_file/112_O_OK",
    ]
    gml_dirs = []
    for base in base_dirs:
        gml_dirs.append(os.path.join(base, "gml"))
        gml_dirs.append(base)
    
    matched_files = []
    for filename in matched['Filename']:
        # 在所有目錄中查找文件
        for gml_dir in gml_dirs:
            file_path = os.path.join(gml_dir, filename)
            if os.path.exists(file_path):
                matched_files.append(file_path)
                break
        else:
            # 若上述固定路徑都找不到，嘗試在 base_dirs 做一次遞迴搜尋（避免資料夾結構差異）
            found_path = None
            for base in base_dirs:
                if not os.path.isdir(base):
                    continue
                for root, _, files in os.walk(base):
                    if filename in files:
                        found_path = os.path.join(root, filename)
                        break
                if found_path:
                    break
            if found_path:
                matched_files.append(found_path)
            else:
                print(f"警告: 找不到原始 GML 檔案 {filename} (已查詢: {gml_dirs})")
    
    return matched_files

def get_building_bounds(building, namespaces):
    """獲取建築物的邊界座標"""
    try:
        # 查找所有 posList 元素
        pos_lists = building.findall('.//gml:posList', namespaces)
        if not pos_lists:
            pos_lists = building.findall('.//*[local-name()="posList"]')
        
        if not pos_lists:
            return None
        
        # 收集所有座標
        all_coords = []
        for pos_list in pos_lists:
            if pos_list.text:
                coords = pos_list.text.strip().split()
                # 確保座標數量是 3 的倍數
                if len(coords) % 3 == 0:
                    # 只取 x, y 座標（忽略 z）
                    coords = [(float(coords[i]), float(coords[i+1])) 
                             for i in range(0, len(coords), 3)]
                    all_coords.extend(coords)
        
        if not all_coords:
            return None
        
        # 計算邊界
        x_coords, y_coords = zip(*all_coords)
        return {
            'min_x': min(x_coords),
            'max_x': max(x_coords),
            'min_y': min(y_coords),
            'max_y': max(y_coords)
        }
    except Exception as e:
        print(f"計算建築物邊界時出錯: {e}")
        return None

def is_building_in_range(building_bounds, x_min, x_max, y_min, y_max):
    """檢查建築物是否在指定範圍內"""
    if not building_bounds:
        return False
    
    # 檢查是否有重疊
    return not (building_bounds['max_x'] < x_min or
               building_bounds['min_x'] > x_max or
               building_bounds['max_y'] < y_min or
               building_bounds['min_y'] > y_max)

def merge_gml_files(main_file, new_file, output_file):
    """合併兩個 GML 文件"""
    # 讀取主文件
    tree1 = ET.parse(main_file)
    root1 = tree1.getroot()
    
    # 讀取新文件
    tree2 = ET.parse(new_file)
    root2 = tree2.getroot()
    
    # 將新文件中的 cityObjectMember 元素添加到主文件中
    for member in root2.findall('.//{http://www.opengis.net/citygml/2.0}cityObjectMember'):
        root1.append(member)
    
    # 更新 boundedBy
    update_bounded_by(root1)
    
    # 保存合併後的文件
    tree1.write(output_file, encoding='utf-8', xml_declaration=True)

def update_bounded_by(root):
    """更新 GML 文件的邊界框"""
    namespaces = {'gml': 'http://www.opengis.net/gml'}
    
    # 收集所有座標
    all_coords = []
    for pos_list in root.findall('.//gml:posList', namespaces):
        if pos_list.text:
            coords = pos_list.text.strip().split()
            if len(coords) % 3 == 0:
                for i in range(0, len(coords), 3):
                    all_coords.append([float(coords[i]), float(coords[i+1]), float(coords[i+2])])
    
    if not all_coords:
        return
    
    # 計算新的邊界
    min_x = min(c[0] for c in all_coords)
    min_y = min(c[1] for c in all_coords)
    min_z = min(c[2] for c in all_coords)
    max_x = max(c[0] for c in all_coords)
    max_y = max(c[1] for c in all_coords)
    max_z = max(c[2] for c in all_coords)
    
    # 更新 boundedBy 元素
    bounded_by = root.find('.//gml:boundedBy', namespaces)
    if bounded_by is not None:
        lower_corner = bounded_by.find('.//gml:lowerCorner', namespaces)
        upper_corner = bounded_by.find('.//gml:upperCorner', namespaces)
        
        if lower_corner is not None and upper_corner is not None:
            lower_corner.text = f"{min_x:.3f} {min_y:.3f} {min_z:.3f}"
            upper_corner.text = f"{max_x:.3f} {max_y:.3f} {max_z:.3f}"

def process_gml_files(matched_gmls, output_dir, output_filename, x_center, y_center, margin_m, excluded_ids=None):
    """處理符合條件的 GML 文件，並將所有建築物合併到一個輸出文件"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # 使用指定的輸出檔名
    output_gml = output_dir / output_filename
    
    # 如果没有提供排除列表，则初始化为空列表
    if excluded_ids is None:
        excluded_ids = []
    
    # 定義查詢範圍
    x_min = x_center - margin_m
    x_max = x_center + margin_m
    y_min = y_center - margin_m
    y_max = y_center + margin_m
    
    # 創建一個臨時文件來存儲所有建築物 ID
    temp_ids_file = output_dir / "temp_building_ids.txt"
    all_building_ids = []
    excluded_count = 0  # 记录被排除的建物数量
    
    print(f"排除的建物 ID 列表: {excluded_ids}" if excluded_ids else "无排除的建物 ID")
    
    # 首先收集所有符合條件的建築物 ID
    for gml_file in matched_gmls:
        try:
            print(f"\n分析文件: {gml_file}")
            
            tree = ET.parse(gml_file)
            root = tree.getroot()
            
            namespaces = {'gml': 'http://www.opengis.net/gml',
                         'bldg': 'http://www.opengis.net/citygml/building/2.0'}
            
            # 嘗試不同的方式查找建築物
            buildings = root.findall('.//bldg:Building', namespaces)
            if not buildings:
                buildings = root.findall('.//*[local-name()="Building"]')
            
            for building in buildings:
                # 檢查建築物是否在範圍內
                bounds = get_building_bounds(building, namespaces)
                if not is_building_in_range(bounds, x_min, x_max, y_min, y_max):
                    continue
                
                # 獲取建築物 ID
                building_id = None
                for id_attr in ['{http://www.opengis.net/gml}id', 'gml:id', 'id']:
                    if id_attr in building.attrib:
                        building_id = building.attrib[id_attr]
                        if building_id.startswith('bldg_'):
                            building_id = building_id[5:]
                        break
                
                if not building_id:
                    for elem in building.findall('.//*'):
                        if elem.tag.endswith('BUILD_ID') and elem.text:
                            building_id = elem.text
                            break
                        elif elem.tag.endswith('name') and elem.text:
                            building_id = elem.text
                            break
                
                if building_id:
                    # 检查是否在排除列表中
                    if building_id in excluded_ids:
                        print(f"排除建物: {building_id}")
                        excluded_count += 1
                        continue
                    
                    all_building_ids.append((gml_file, building_id))
            
        except Exception as e:
            print(f"處理文件 {gml_file} 時出錯: {e}")
    
    if not all_building_ids:
        print("未找到符合範圍的建築物")
        return
    
    print(f"\n共找到 {len(all_building_ids)} 個符合範圍的建築物")
    if excluded_count > 0:
        print(f"排除了 {excluded_count} 個不需要的建築物")
    
    # 為每個源文件創建並處理建築物
    for gml_file, building_ids in itertools.groupby(all_building_ids, key=lambda x: x[0]):
        # 提取當前文件的建築物 ID
        current_ids = [bid for _, bid in building_ids]
        
        if not current_ids:
            continue
            
        print(f"\n從 {gml_file} 提取 {len(current_ids)} 個建築物")
        
        # 將當前的建築物 ID 寫入臨時文件
        with open(temp_ids_file, 'w', encoding='utf-8') as f:
            for bid in current_ids:
                f.write(f"ID: {bid}\n")
        
        # 如果是第一個文件，直接輸出到目標文件
        # 如果不是第一個文件，則需要合併到現有文件中
        if not output_gml.exists():
            extract_buildings_from_gml(gml_file, current_ids, str(output_gml))
        else:
            # 創建臨時文件
            temp_output = output_dir / "temp_output.gml"
            extract_buildings_from_gml(gml_file, current_ids, str(temp_output))
            
            # 合併文件
            merge_gml_files(str(output_gml), str(temp_output), str(output_gml))
            
            # 刪除臨時文件
            temp_output.unlink()
    
    # 清理臨時文件
    if temp_ids_file.exists():
        temp_ids_file.unlink()
    
    # 移除空行
    with open(output_gml, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    cleaned_lines = [line for line in lines if line.strip()]
    with open(output_gml, 'w', encoding='utf-8') as f:
        f.writelines(cleaned_lines)
    
    print(f"\n所有建築物已合併到: {output_gml}")

if __name__ == "__main__":
    # 使用者輸入
    lat = float(input("請輸入緯度 (例如 24.78703): "))
    lon = float(input("請輸入經度 (例如 120.99693): "))
    margin_m = float(input("請輸入匡列範圍半徑（單位：公尺，例如 200）: "))
    output_filename = input("請輸入輸出的 GML 檔案名稱 (例如 NYCU_EU_test.gml): ")
    
    # 詢問是否有要排除的建物 ID
    exclude_input = input("請輸入要排除的建物 ID (用逗號分隔，直接按 Enter 跳過): ").strip()
    excluded_ids = []
    if exclude_input:
        excluded_ids = [bid.strip() for bid in exclude_input.split(',') if bid.strip()]
    
    # 同時讀取配置文件中的排除ID
    file_excluded_ids = read_excluded_ids_from_file()
    
    # 合併手動輸入和文件中的排除ID
    all_excluded_ids = list(set(excluded_ids + file_excluded_ids))  # 使用set去除重複
    
    if all_excluded_ids:
        print(f"總共將排除 {len(all_excluded_ids)} 個建物ID: {all_excluded_ids}")
    else:
        print("未設定任何要排除的建物ID")
    
    # 轉換座標
    x_center, y_center = wgs84_to_epsg3826(lat, lon)
    
    # 設定路徑
    csv_path = "gml_bounding_boxes_v1.csv"
    output_dir = "processed_gmls"
    
    # 找到符合範圍的 GML 文件
    matched_gmls = find_matching_gmls(csv_path, lat, lon, margin_m)
    print(f"找到 {len(matched_gmls)} 個符合條件的 GML 文件")
    
    # 處理符合條件的文件
    process_gml_files(matched_gmls, output_dir, output_filename, x_center, y_center, margin_m, all_excluded_ids) 