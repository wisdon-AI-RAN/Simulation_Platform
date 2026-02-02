import xml.etree.ElementTree as ET
import re
from pathlib import Path
import os
from xml.dom import minidom
import copy

def read_building_ids(building_ids_file):
    """從文件中讀取建築物 ID 列表"""
    building_ids = []
    with open(building_ids_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('ID:'):
                building_id = line.split('ID:')[1].strip()
                building_ids.append(building_id)
            elif line.startswith('main:'):
                building_id = line.split('main:')[1].strip()
                building_ids.append(building_id)
    return building_ids

def get_lowest_z(building_element, namespaces):
    """獲取建築物所有座標中最低的 z 值"""
    try:
        # 查找所有 posList 元素
        poslist_elements = building_element.findall('.//gml:posList', namespaces)
        if not poslist_elements:
            poslist_elements = building_element.findall('.//*', namespaces)
            poslist_elements = [elem for elem in poslist_elements if elem.tag.endswith('posList')]
        
        lowest_z = float('inf')  # 初始化為無限大
        
        for poslist in poslist_elements:
            if poslist.text:
                # 分割座標
                coords = poslist.text.strip().split()
                # 確保座標數量是 3 的倍數
                if len(coords) % 3 == 0:
                    # 獲取所有 z 座標
                    z_coords = [float(coords[i]) for i in range(2, len(coords), 3)]
                    # 更新最低 z 值
                    if z_coords:
                        current_min = min(z_coords)
                        lowest_z = min(lowest_z, current_min)
        
        return lowest_z if lowest_z != float('inf') else None
        
    except Exception as e:
        print(f"計算最低 z 座標時出錯: {e}")
        return None

def extract_buildings_from_gml(source_gml, building_ids, output_gml):
    """
    從源 GML 文件中提取指定建築物 ID 的資訊，並完整複製到輸出 GML 文件
    同時自動生成底面（floor）信息
    
    Args:
        source_gml (str): 源 GML 文件路徑
        building_ids (list): 要提取的建築物 ID 列表
        output_gml (str): 輸出 GML 文件路徑
    """
    print(f"從 {source_gml} 提取建築物: {', '.join(building_ids)}")
    
    # 解析源 GML 文件
    try:
        tree = ET.parse(source_gml)
        root = tree.getroot()
    except Exception as e:
        print(f"解析源 GML 文件時出錯: {e}")
        return
    
    # 從源文件提取命名空間
    namespaces = {}
    for prefix, uri in root.attrib.items():
        if prefix.startswith('xmlns:'):
            ns_prefix = prefix.split(':')[1]
            namespaces[ns_prefix] = uri
    
    # 確保有基本的命名空間
    if 'core' not in namespaces:
        namespaces['core'] = "http://www.opengis.net/citygml/2.0"
    if 'gml' not in namespaces:
        namespaces['gml'] = "http://www.opengis.net/gml"
    if 'bldg' not in namespaces:
        namespaces['bldg'] = "http://www.opengis.net/citygml/building/2.0"
    if 'xsi' not in namespaces:
        namespaces['xsi'] = "http://www.w3.org/2001/XMLSchema-instance"
    if 'xlink' not in namespaces:
        namespaces['xlink'] = "http://www.w3.org/1999/xlink"
    
    # 創建新的 XML 根元素，保留源文件的命名空間
    new_root = ET.Element("{http://www.opengis.net/citygml/2.0}CityModel")
    for prefix, uri in namespaces.items():
        new_root.set(f"xmlns:{prefix}", uri)
    
    if 'xsi' in namespaces:
        new_root.set("xsi:schemaLocation", "http://www.opengis.net/citygml/2.0 http://schemas.opengis.net/citygml/2.0/cityGMLBase.xsd")
    
    # 從源文件複製 boundedBy 元素
    bounded_by = root.find('.//gml:boundedBy', namespaces)
    if bounded_by is not None:
        # 使用 ET.tostring 和 ET.fromstring 來完整複製元素
        bounded_by_str = ET.tostring(bounded_by, encoding='unicode')
        new_bounded_by = ET.fromstring(bounded_by_str)
        new_root.append(new_bounded_by)
    
    
    # 找到所有 cityObjectMember 元素
    city_object_members = []
    try:
        city_object_members = root.findall('.//core:cityObjectMember', namespaces)
    except:
        pass
    
    if not city_object_members:
        try:
            city_object_members = root.findall('.//*', namespaces)
            city_object_members = [elem for elem in city_object_members if elem.tag.endswith('cityObjectMember')]
        except:
            pass
    
    # 檢查所有建築物是否存在
    missing_buildings = []
    found_buildings = []
    
    for city_object_member in city_object_members:
        # 在 cityObjectMember 中查找建築物
        building = None
        building_id = None
        
        # 嘗試不同的方式查找建築物
        try:
            buildings = city_object_member.findall('.//bldg:Building', namespaces)
            if buildings:
                building = buildings[0]
        except:
            pass
        
        if building is None:
            try:
                buildings = city_object_member.findall('.//*', namespaces)
                buildings = [elem for elem in buildings if elem.tag.endswith('Building')]
                if buildings:
                    building = buildings[0]
            except:
                pass
        
        if building is not None:
            # 嘗試從不同的屬性中獲取建築物 ID
            for id_attr in ['{http://www.opengis.net/gml}id', 'id', 'gml:id']:
                if id_attr in building.attrib:
                    building_id = building.attrib[id_attr]
                    # 如果 ID 以 "bldg_" 開頭，去掉前綴
                    if building_id.startswith('bldg_'):
                        building_id = building_id[5:]
                    break
            
            # 如果沒有從屬性中找到 ID，嘗試從子元素中查找
            if building_id is None:
                try:
                    id_elements = building.findall('.//BUILD_ID', namespaces)
                    if id_elements and id_elements[0].text:
                        building_id = id_elements[0].text
                except:
                    pass
            
            if building_id is None:
                try:
                    id_elements = building.findall('.//gml:name', namespaces)
                    if id_elements and id_elements[0].text:
                        building_id = id_elements[0].text
                except:
                    pass
            
            if building_id is None:
                try:
                    id_elements = building.findall('.//*', namespaces)
                    id_elements = [elem for elem in id_elements if elem.tag.endswith('name') or elem.tag.endswith('BUILD_ID')]
                    if id_elements and id_elements[0].text:
                        building_id = id_elements[0].text
                except:
                    pass
        
        # 如果找到了建築物 ID，檢查是否在要提取的列表中
        if building_id is not None and building_id in building_ids:
            # 檢查建築物的最低 z 值
            lowest_z = get_lowest_z(building, namespaces)
            if lowest_z is None or abs(lowest_z) > 0.001:  # 使用小的閾值來判斷是否為 0
                print(f"跳過建築物 {building_id}：最低 z 值為 {lowest_z}，不是地面建築")
                continue
                
            print(f"找到建築物: {building_id}")
            found_buildings.append(building_id)
            
            # 使用 ET.tostring 和 ET.fromstring 來完整複製 cityObjectMember 元素
            city_object_member_str = ET.tostring(city_object_member, encoding='unicode')
            new_city_object_member = ET.fromstring(city_object_member_str)
            
            # 修改建築物 ID，添加 bldg_ 前綴
            try:
                # 查找建築物元素
                building_elems = new_city_object_member.findall('.//*', namespaces)
                for elem in building_elems:
                    if elem.tag.endswith('Building'):
                        # 修改 gml:id 屬性
                        for attr_name, attr_value in elem.attrib.items():
                            if attr_name.endswith('id'):
                                if not attr_value.startswith('bldg_'):
                                    elem.attrib[attr_name] = f"bldg_{attr_value}"
                                break
            except Exception as e:
                print(f"修改建築物 ID 時出錯: {e}")
            
            # 在新的 cityObjectMember 中查找 lod1Solid 元素
            lod1_solid = None
            try:
                lod1_solids = new_city_object_member.findall('.//bldg:lod1Solid', namespaces)
                if lod1_solids:
                    lod1_solid = lod1_solids[0]
            except:
                pass
            
            if lod1_solid is None:
                try:
                    lod1_solids = new_city_object_member.findall('.//*', namespaces)
                    lod1_solids = [elem for elem in lod1_solids if elem.tag.endswith('lod1Solid')]
                    if lod1_solids:
                        lod1_solid = lod1_solids[0]
                except:
                    pass
            
            if lod1_solid is not None:
                # 在 lod1Solid 中查找 CompositeSurface 元素
                composite_surface = None
                try:
                    composite_surfaces = lod1_solid.findall('.//gml:CompositeSurface', namespaces)
                    if composite_surfaces:
                        composite_surface = composite_surfaces[0]
                except:
                    pass
                
                if composite_surface is None:
                    try:
                        composite_surfaces = lod1_solid.findall('.//*', namespaces)
                        composite_surfaces = [elem for elem in composite_surfaces if elem.tag.endswith('CompositeSurface')]
                        if composite_surfaces:
                            composite_surface = composite_surfaces[0]
                    except:
                        pass
                
                if composite_surface is not None:
                    roof_element = None
                    matched_type = None  # 用來記錄是匹配到 Roof 還是 S_0

                    try:
                        target_ids = {
                            f"ID_{building_id}_Roof": "Roof",
                            f"ID_{building_id}_S_0": "S_0"
                        }

                        for elem in composite_surface.findall('.//*', namespaces):
                            for attr_name, attr_value in elem.attrib.items():
                                if attr_value in target_ids and elem.tag.endswith('CompositeSurface'):
                                    roof_element = elem
                                    matched_type = target_ids[attr_value]  # 儲存是哪一個類型
                                    break
                            if roof_element is not None:
                                break

                    except Exception as e:
                        print(f"[WARN] 查找過程出錯: {e}")

                    
                    # 如果找到了 Roof 元素，創建 Floor 元素
                    if roof_element is not None:
                        if matched_type == "Roof":
                            print("找到 Roof 元素，創建 Floor 元素")
                        elif matched_type == "S_0":
                            print(" 找到 S_0 元素，創建 Floor 元素")
                        
                        # 創建 Floor 元素
                        floor_element = copy.deepcopy(roof_element)
                        
                        # 修改 ID
                        for attr_name, attr_value in floor_element.attrib.items():
                            if attr_value == f"ID_{building_id}_Roof":
                                floor_element.attrib[attr_name] = f"ID_{building_id}_floor"
                                break
                        
                        # 修改所有 posList 元素的 z 座標為 0
                        try:
                            poslist_elements = floor_element.findall('.//gml:posList', namespaces)
                            if not poslist_elements:
                                poslist_elements = floor_element.findall('.//*', namespaces)
                                poslist_elements = [elem for elem in poslist_elements if elem.tag.endswith('posList')]
                            
                            for poslist in poslist_elements:
                                if poslist.text:
                                    # 分割座標
                                    coords = poslist.text.strip().split()
                                    # 確保座標數量是 3 的倍數
                                    if len(coords) % 3 == 0:
                                        # 修改 z 座標為 0
                                        for i in range(2, len(coords), 3):
                                            coords[i] = "0.000000"
                                        # 更新 posList 文本
                                        poslist.text = "\n                          " + " ".join(coords) + "\n                          "
                        except:
                            pass
                        
                        # 將 Floor 元素添加到 CompositeSurface 中
                        try:
                            # 創建新的 surfaceMember 元素
                            new_surface_member = ET.Element("{http://www.opengis.net/gml}surfaceMember")
                            # 添加 Floor 元素到新的 surfaceMember 元素
                            new_surface_member.append(floor_element)
                            # 添加新的 surfaceMember 元素到 CompositeSurface
                            composite_surface.append(new_surface_member)
                            print("成功添加 Floor 元素")
                        except Exception as e:
                            print(f"添加 Floor 元素時出錯: {e}")
            
            # 將修改後的 cityObjectMember 添加到新的根元素
            new_root.append(new_city_object_member)
    
    # 檢查是否有建築物未找到
    for building_id in building_ids:
        if building_id not in found_buildings:
            missing_buildings.append(building_id)
    
    if missing_buildings:
        print(f"以下建築物在源文件中不存在: {', '.join(missing_buildings)}")
        if not found_buildings:
            print("沒有找到任何建築物，停止處理")
            return
    
    # 使用 minidom 美化 XML 輸出
    rough_string = ET.tostring(new_root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    
    # 移除空行
    cleaned_lines = [line for line in pretty_xml.splitlines() if line.strip()]
    cleaned_xml = '\n'.join(cleaned_lines)
    
    # 寫入輸出文件
    with open(output_gml, 'w', encoding='utf-8') as f:
        f.write(cleaned_xml)
    
    print(f"已將轉換後的文件保存到: {output_gml}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("使用方法:")
        print("從大文件提取建築物: python gml_transport_v2.py extract <source_gml> <building_ids_file> <output_gml>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "extract":
        if len(sys.argv) < 5:
            print("使用方法: python gml_transport_v2.py extract <source_gml> <building_ids_file> <output_gml>")
            sys.exit(1)
        
        source_gml = sys.argv[2]
        building_ids_file = sys.argv[3]
        output_gml = sys.argv[4]
        
        building_ids = read_building_ids(building_ids_file)
        extract_buildings_from_gml(source_gml, building_ids, output_gml)
    
    else:
        print("未知命令: " + command)
        print("使用方法:")
        print("從大文件提取建築物: python gml_transport_v2.py extract <source_gml> <building_ids_file> <output_gml>")