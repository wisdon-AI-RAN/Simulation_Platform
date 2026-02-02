#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from pyproj import Transformer
import os
import logging

logger = logging.getLogger(__name__)

class OBJToGMLConverter:
    def __init__(self):
        self.vertices = []  # (x, y, z)
        self.faces = []     # [(v1, v2, v3, v4), ...]
        self.objects = []   # object info
        
    def parse_obj(self, obj_file_path):
        """解析OBJ文件"""
        self.vertices = []
        self.faces = []
        self.objects = []
        
        current_object = None
        
        logger.info(f"正在解析OBJ文件: {obj_file_path}")
        
        try:
            with open(obj_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                        
                    parts = line.split()
                    
                    if parts[0] == 'o':  # 对象名称
                        if current_object:
                            current_object['vertex_end'] = len(self.vertices)
                            self.objects.append(current_object)
                        
                        current_object = {
                            'name': parts[1],
                            'vertex_start': len(self.vertices),
                            'faces': []
                        }
                        
                    elif parts[0] == 'v':  # 顶点
                        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                        self.vertices.append((x, y, z))
                        
                    elif parts[0] == 'f':  # 面
                        face_vertices = []
                        for vertex_data in parts[1:]:
                            # OBJ 1-based index -> 0-based
                            vertex_index = int(vertex_data.split('/')[0]) - 1
                            face_vertices.append(vertex_index)
                        
                        if current_object:
                            current_object['faces'].append(face_vertices)
                        else:
                            # Handle faces without 'o' declaration (common in simple OBJs)
                            if not self.objects and not current_object:
                                current_object = {
                                    'name': 'DefaultObject',
                                    'vertex_start': 0,
                                    'faces': []
                                }
                            if current_object:
                                current_object['faces'].append(face_vertices)
                        
                        self.faces.append(face_vertices)
            
            if current_object:
                current_object['vertex_end'] = len(self.vertices)
                self.objects.append(current_object)
                
            logger.info(f"解析完成：{len(self.vertices)} 个顶点，{len(self.faces)} 个面，{len(self.objects)} 个对象")
            
        except Exception as e:
            logger.error(f"解析 OBJ 失敗: {e}")
            raise

    def calculate_bounds(self):
        """计算边界盒"""
        if not self.vertices:
            return (0, 0, 0, 0, 0, 0)
            
        min_x = min(v[0] for v in self.vertices)
        max_x = max(v[0] for v in self.vertices)
        min_y = min(v[1] for v in self.vertices)
        max_y = max(v[1] for v in self.vertices)
        min_z = min(v[2] for v in self.vertices)
        max_z = max(v[2] for v in self.vertices)
        
        return (min_x, min_y, min_z, max_x, max_y, max_z)

    def create_gml(self, output_file_path, epsg_code, offset_x, offset_y):
        """创建GML文件"""
        logger.info(f"正在创建GML文件: {output_file_path}, Offset: ({offset_x}, {offset_y})")
        
        min_x, min_y, min_z, max_x, max_y, max_z = self.calculate_bounds()
        
        adjusted_min_x = min_x + offset_x
        adjusted_max_x = max_x + offset_x
        adjusted_min_y = min_y + offset_y
        adjusted_max_y = max_y + offset_y
        
        # 创建根元素
        root = ET.Element('ns0:CityModel')
        root.set('xmlns:ns0', 'http://www.opengis.net/citygml/2.0')
        root.set('xmlns:ns1', 'http://www.opengis.net/gml')
        root.set('xmlns:ns2', 'http://www.opengis.net/citygml/building/2.0')
        root.set('xmlns:core', 'http://www.opengis.net/citygml/2.0')
        root.set('xmlns:gml', 'http://www.opengis.net/gml')
        root.set('xmlns:bldg', 'http://www.opengis.net/citygml/building/2.0')
        
        bounded_by = ET.SubElement(root, 'ns1:boundedBy')
        envelope = ET.SubElement(bounded_by, 'ns1:Envelope')
        envelope.set('srsDimension', '3')
        envelope.set('srsName', f'urn:ogc:def:crs:EPSG::{epsg_code}')
        
        lower_corner = ET.SubElement(envelope, 'ns1:lowerCorner')
        lower_corner.text = f"{adjusted_min_x:.3f} {adjusted_min_y:.3f} {min_z:.3f}"
        
        upper_corner = ET.SubElement(envelope, 'ns1:upperCorner')
        upper_corner.text = f"{adjusted_max_x:.3f} {adjusted_max_y:.3f} {max_z:.3f}"
        
        for obj_idx, obj in enumerate(self.objects):
            city_object_member = ET.SubElement(root, 'ns0:cityObjectMember')
            building = ET.SubElement(city_object_member, 'ns2:Building')
            building.set('ns1:id', obj['name'])
            
            name_elem = ET.SubElement(building, 'ns1:name')
            name_elem.text = obj['name']
            
            # Using custom tags as per original script, though mostly not standard CityGML without proper xsd
            build_id = ET.SubElement(building, 'BUILD_ID')
            build_id.text = obj['name']
            
            build_h = ET.SubElement(building, 'BUILD_H')
            build_h.text = f"{max_z - min_z:.2f}"
            
            model_lod = ET.SubElement(building, 'MODEL_LOD')
            model_lod.text = "2"
            
            lod1_solid = ET.SubElement(building, 'ns2:lod1Solid')
            solid = ET.SubElement(lod1_solid, 'ns1:Solid')
            exterior = ET.SubElement(solid, 'ns1:exterior')
            composite_surface = ET.SubElement(exterior, 'ns1:CompositeSurface')
            
            for face_idx, face in enumerate(obj['faces']):
                surface_member = ET.SubElement(composite_surface, 'ns1:surfaceMember')
                comp_surface = ET.SubElement(surface_member, 'ns1:CompositeSurface')
                comp_surface.set('ns1:id', f"ID_{obj['name']}_face_{face_idx}")
                
                surface_member_inner = ET.SubElement(comp_surface, 'ns1:surfaceMember')
                polygon = ET.SubElement(surface_member_inner, 'ns1:Polygon')
                exterior_ring = ET.SubElement(polygon, 'ns1:exterior')
                linear_ring = ET.SubElement(exterior_ring, 'ns1:LinearRing')
                pos_list = ET.SubElement(linear_ring, 'ns1:posList')
                pos_list.set('srsDimension', '3')
                
                coords = []
                for vertex_idx in face:
                    if vertex_idx < len(self.vertices):
                        x, y, z = self.vertices[vertex_idx]
                        adj_x = x + offset_x
                        adj_y = y + offset_y
                        coords.append(f"{adj_x:.6f} {adj_y:.6f} {z:.6f}")
                
                # Close polygon
                if coords and len(face) > 2:
                    first_vertex_idx = face[0]
                    if first_vertex_idx < len(self.vertices):
                        x, y, z = self.vertices[first_vertex_idx]
                        adj_x = x + offset_x
                        adj_y = y + offset_y
                        coords.append(f"{adj_x:.6f} {adj_y:.6f} {z:.6f}")
                
                pos_list.text = ' '.join(coords)
        
        rough_string = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logger.info(f"GML文件已成功创建: {output_file_path}")

    def process(self, obj_path, gml_path, lat, lon, epsg_code="3826"):
        """主入口
        lat, lon: WGS84 座標, 將作為模型原點(0,0,0)的地理位置
        epsg_code: 目標投影座標系 (預設 3826 TWD97)
        """
        # 1. 計算 Offset (Lat/Lon -> EPSG)
        try:
            transformer = Transformer.from_crs("epsg:4326", f"epsg:{epsg_code}", always_xy=True)
            # always_xy=True means transform(lon, lat)
            offset_x, offset_y = transformer.transform(lon, lat)
            logger.info(f"座標轉換: ({lat}, {lon}) -> EPSG:{epsg_code} ({offset_x}, {offset_y})")
            
            # 2. 解析
            self.parse_obj(obj_path)
            
            # 3. 生成
            self.create_gml(gml_path, epsg_code, offset_x, offset_y)
            return True
        except Exception as e:
            logger.error(f"Process Error: {e}")
            raise
