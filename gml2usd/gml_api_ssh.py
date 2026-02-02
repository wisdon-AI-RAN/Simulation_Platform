#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_file
import subprocess
import os
import time
import io
import logging
import argparse
from logging.handlers import RotatingFileHandler
import datetime
import traceback
import sys
from local_citygml2usd import convert_citygml_to_usd, ConversionError
from obj_converter import OBJToGMLConverter, validate_obj_required_objects, OBJValidationError
from usd_to_gltf import usd_to_glb, usd_to_gltf_zip, usd_to_gltf_dir, usd_to_gltf_single_file
import requests
import re


def _zip_files(zip_path: str, files: list[tuple[str, str]]) -> None:
    """Create a zip that contains a set of files.

    files: list of (arcname, filepath)
    """
    import zipfile

    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, filepath in files:
            zf.write(filepath, arcname=arcname)

# 创建日志目录
os.makedirs('logs', exist_ok=True)

# 配置日志
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
log_file = 'logs/gml_api.log'

# 创建滚动日志处理器，限制单个日志文件大小为10MB，保留10个备份文件
file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=10)
file_handler.setFormatter(log_formatter)

# 控制台日志处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# 根日志配置
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = Flask(__name__)


def _safe_base_name(filename: str | None, *, default: str = "output") -> str:
    """Derive a filesystem/zip-safe base name (no extension)."""
    if not filename:
        return default
    base = os.path.splitext(os.path.basename(str(filename)))[0].strip()
    if not base:
        return default
    # Keep simple, portable characters.
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    base = base.strip("._-")
    return base or default


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "":
        return default
    return text in {"1", "true", "t", "yes", "y", "on"}

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    response = {
        "status": "healthy", 
        "version": "1.0",
        "timestamp": datetime.datetime.now().isoformat()
    }
    logger.info(f"健康检查: {response}")
    return jsonify(response)

@app.route('/process_gml', methods=['POST'])
def process_gml():
    """GML处理接口"""
    try:
        # 获取请求参数
        logger.info(f"收到請求")

        data = request.get_json()
        if not data:
            return jsonify({
                "status": "error",
                "message": "wrong format"
            }), 400

        project_id = data.get('project_id','0')
        default_gml_name = f"map_aodt_{project_id}.gml"

        
        lat = data.get('lat', 24.78703)
        lon = data.get('lon', 120.99693)
        margin = data.get('margin', 200)
        gml_name = data.get('gml_name', default_gml_name)
        epsg_in = data.get('epsg_in', '3826')
        epsg_out = data.get('epsg_out', '32654')
        disable_interiors = _parse_bool(data.get('disable_interiors', False), default=False)
        keep_files = _parse_bool(data.get('keep_files', False), default=False)
        output_raw = data.get('output', None)
        output_format = (str(output_raw).strip().lower() if output_raw is not None else '')

        # Ensure output directories exist (host volume mounts may not be present on a fresh machine)
        os.makedirs(os.path.join("processed_gmls"), exist_ok=True)
        os.makedirs(os.path.join("processed_usds"), exist_ok=True)

        #設定local的usd位置
        usd_name = gml_name.split(".gml")[0] + ".usd"
        working_file = os.path.abspath(__file__)
        working_dir = os.path.dirname(working_file)
        usd_path = os.path.join(working_dir,f"processed_usds/{usd_name}")
   

        # 记录请求信息
        logger.info(
            f"收到处理请求: lat={lat}, lon={lon}, margin={margin}, gml_name={gml_name}, "
            f"disable_interiors={disable_interiors}, keep_files={keep_files}"
        )
        
        # Step 1: generate GML locally (Main.py is interactive; we feed stdin)
        cmd = [
            'python3', 'Main.py'
        ]
        

        
        # 记录即将执行的命令
        logger.info(f"执行命令: {' '.join(cmd)}")
        
        # 执行命令
        # Feed interactive answers to Main.py
        inputs = f"{lat}\n{lon}\n{margin}\n{gml_name}\n\n".encode()
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_dir,
        )
        
        # 读取输出
        stdout_bytes, stderr_bytes = process.communicate(inputs)
        stdout = stdout_bytes.decode(errors='replace')
        stderr = stderr_bytes.decode(errors='replace')
        
        # 检查是否成功
        if process.returncode != 0:
            logger.error(f"处理失败: {stderr}")
            return jsonify({
                "status": "error",
                "message": f"process fail: {stderr}",
                "details": stdout
            }), 500

        # Verify GML was actually generated before converting to USD.
        gml_path = os.path.join(working_dir, "processed_gmls", gml_name)
        if not os.path.exists(gml_path):
            logger.error(
                "Main.py completed but expected GML file is missing: %s; stdout=%s; stderr=%s",
                gml_path,
                stdout[-2000:],
                stderr[-2000:],
            )
            try:
                existing = os.listdir(os.path.join(working_dir, "processed_gmls"))
            except Exception:
                existing = []
            return jsonify({
                "status": "error",
                "message": "GML generation failed (file not created)",
                "expected_gml": os.path.join("processed_gmls", gml_name),
                "processed_gmls_listing": existing,
                "stdout_tail": stdout[-2000:],
                "stderr_tail": stderr[-2000:],
            }), 500

        # Step 2: convert GML -> USD locally in this container
        try:
            convert_citygml_to_usd(
                gml_path=os.path.join("processed_gmls", gml_name),
                usd_path=usd_path,
                epsg_in=str(epsg_in),
                epsg_out=str(epsg_out),
                rough=True,
                disable_interiors=disable_interiors,
            )
        except ConversionError as conv_err:
            logger.error(f"USD 转换失败: {conv_err}")
            return jsonify({
                "status": "error",
                "message": "USD conversion failed",
                "details": str(conv_err),
                "expected_gml": os.path.join("processed_gmls", gml_name),
            }), 500
        
        
        # 检查GML,USD文件是否已创建
        gml_path = os.path.join("processed_gmls", gml_name)
        if not os.path.exists(gml_path):
            logger.error(f"未能找到生成的GML文件: {gml_path}")
            return jsonify({
                "status": "error",
                "message": f"未能找到生成的GML文件 {gml_path}",
                "details": stdout
            }), 404
        if not os.path.exists(usd_path):
            logger.error(f"未能找到生成的USD文件: {usd_path}")
            return jsonify({
                "status": "error",
                "message": f"未能找到生成的USD文件 {usd_path}",
                "details": stdout
            }), 404

        # 获取文件大小
        file_size = os.path.getsize(gml_path)
        
        # 检查文件是否为空或非常小(可能只有XML头)
        if file_size < 300:  # 假设有效GML文件至少300字节
            logger.warning(f"GML文件已生成但没有建筑物数据: {gml_path}, 大小: {file_size}字节")
        else:
            logger.info(f"GML文件已成功生成: {gml_path}, 大小: {file_size}字节")

        # Return files and delete the files
        # Default: if output is not specified, return a bundle zip (USD + glTF assets)
        if output_format == '':
            bundle_dir = os.path.join(working_dir, "processed_bundles")
            os.makedirs(bundle_dir, exist_ok=True)

            tmp_gltf_dir = os.path.join(bundle_dir, os.path.splitext(usd_name)[0] + "_gltf")
            generated = usd_to_gltf_dir(usd_path, tmp_gltf_dir, base_name=os.path.splitext(usd_name)[0])

            bundle_zip_path = os.path.join(bundle_dir, os.path.splitext(usd_name)[0] + "_bundle.zip")
            files = [(os.path.basename(usd_path), usd_path)]
            for f in generated:
                files.append((os.path.basename(f), f))
            _zip_files(bundle_zip_path, files)

            return_data = io.BytesIO()
            with open(bundle_zip_path, 'rb') as fo:
                return_data.write(fo.read())
            return_data.seek(0)

            os.remove(bundle_zip_path)
            for f in generated:
                try:
                    os.remove(f)
                except Exception:
                    pass
            try:
                os.rmdir(tmp_gltf_dir)
            except Exception:
                pass
            if not keep_files:
                os.remove(usd_path)
                os.remove(gml_path)
            return send_file(return_data, mimetype='application/zip', download_name=os.path.basename(bundle_zip_path))

        if output_format in {'glb', 'gltf', 'gltf_zip'}:
            gltf_out_dir = os.path.join(working_dir, "processed_gltfs")
            os.makedirs(gltf_out_dir, exist_ok=True)

            if output_format == 'glb':
                glb_path = os.path.join(gltf_out_dir, os.path.splitext(usd_name)[0] + ".glb")
                usd_to_glb(usd_path, glb_path)
                return_data = io.BytesIO()
                with open(glb_path, 'rb') as fo:
                    return_data.write(fo.read())
                return_data.seek(0)
                os.remove(glb_path)
                if not keep_files:
                    os.remove(usd_path)
                    os.remove(gml_path)
                return send_file(return_data, mimetype='model/gltf-binary', download_name=os.path.basename(glb_path))

            if output_format == 'gltf':
                gltf_path = os.path.join(gltf_out_dir, os.path.splitext(usd_name)[0] + ".gltf")
                usd_to_gltf_single_file(usd_path, gltf_path, base_name=os.path.splitext(usd_name)[0])
                return_data = io.BytesIO()
                with open(gltf_path, 'rb') as fo:
                    return_data.write(fo.read())
                return_data.seek(0)
                os.remove(gltf_path)
                if not keep_files:
                    os.remove(usd_path)
                    os.remove(gml_path)
                return send_file(return_data, mimetype='model/gltf+json', download_name=os.path.basename(gltf_path))

            zip_path = os.path.join(gltf_out_dir, os.path.splitext(usd_name)[0] + "_gltf.zip")
            usd_to_gltf_zip(usd_path, zip_path, base_name=os.path.splitext(usd_name)[0])
            return_data = io.BytesIO()
            with open(zip_path, 'rb') as fo:
                return_data.write(fo.read())
            return_data.seek(0)
            os.remove(zip_path)
            if not keep_files:
                os.remove(usd_path)
                os.remove(gml_path)
            return send_file(return_data, mimetype='application/zip', download_name=os.path.basename(zip_path))

        # Default / explicit USD output
        return_data = io.BytesIO()
        with open(usd_path,'rb') as fo:
            return_data.write(fo.read())
        return_data.seek(0)
        if not keep_files:
            os.remove(usd_path)
            os.remove(gml_path)
        return send_file(return_data, mimetype='application/octet-stream')
    
    except Exception as e:
        # 记录异常堆栈
        error_trace = traceback.format_exc()
        logger.error(f"处理请求时发生错误: {str(e)}\n{error_trace}")
        return jsonify({
            "status": "error",
            "message": f"内部服务器错误: {str(e)}",
            "stack_trace": error_trace
        }), 500
    
@app.route('/process_obj', methods=['POST'])
def process_obj():
    """OBJ处理接口 - 接收OBJ並轉換為USD (經由GML)
    Required form-data: 
      - obj_file: The .obj file
      - lat: Origin latitude (WGS84)
      - lon: Origin longitude (WGS84)
    Optional:
      - project_id: ID
      - epsg_gml: EPSG code for intermediate GML (default 3826)
      - epsg_usd: EPSG code for final USD (default 32654)
            - output: 'gml' or 'usd' (default 'usd')
            - keep_files: '1' to keep temp files (default cleanup)
    """
    try:
        logger.info(f"收到 OBJ 處理請求")
        
        # 1. 檢查檔案
        if 'obj_file' not in request.files:
            return jsonify({"status": "error", "message": "No obj_file part"}), 400
            
        file = request.files['obj_file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"}), 400

        # 2. 取得參數
        project_id = request.form.get('project_id', f"obj_{int(time.time())}")
        lat_str = request.form.get('lat')
        lon_str = request.form.get('lon')
        epsg_gml = request.form.get('epsg_gml', '3826') 
        epsg_usd = request.form.get('epsg_usd', '32654')
        disable_interiors = _parse_bool(request.form.get('disable_interiors', None), default=False)
        skip_obj_validation = _parse_bool(request.form.get('skip_obj_validation', None), default=False)
        # Converter script inside /opt/aodt_ui_gis
        # Default: indoor + groundplane + domain pipeline.
        script_name = (
            request.form.get('script_name', 'citygml2aodt_indoor_groundplane_domain.py')
            or 'citygml2aodt_indoor_groundplane_domain.py'
        ).strip()
        output_raw = request.form.get('output')
        output_format = (output_raw.strip().lower() if isinstance(output_raw, str) else '')
        keep_files = (request.form.get('keep_files', '0') or '0').strip() == '1'

        # Naming for responses: default to uploaded OBJ stem (e.g. Askey.obj -> Askey.*)
        # You can override with output_basename=form field.
        response_base = _safe_base_name(request.form.get('output_basename'), default="")
        if not response_base:
            response_base = _safe_base_name(file.filename, default=_safe_base_name(project_id, default="output"))

        # Optional validation: ensure OBJ contains specific object/group names.
        # - required_objects: comma-separated list, e.g. "floor,roof"
        # - required_object: repeatable field, e.g. -F required_object=floor -F required_object=roof
        required_objects = []
        required_objects_csv = request.form.get('required_objects')
        if required_objects_csv:
            required_objects.extend([x.strip() for x in required_objects_csv.split(',') if x.strip()])
        required_objects.extend([x.strip() for x in request.form.getlist('required_object') if x.strip()])

        # Default behavior: enforce common key elements unless user explicitly skips validation.
        if not required_objects and not skip_obj_validation:
            required_objects = ['floor', 'roof']
        
        if not lat_str or not lon_str:
             return jsonify({"status": "error", "message": "Missing lat or lon parameters"}), 400
             
        lat = float(lat_str)
        lon = float(lon_str)

        # 3. 準備路徑
        working_file = os.path.abspath(__file__)
        working_dir = os.path.dirname(working_file)
        
        # Keep temp filenames unique-ish to reduce collisions across concurrent requests.
        tmp_suffix = f"{project_id}_{int(time.time())}"
        obj_filename = f"{tmp_suffix}.obj"
        gml_filename = f"map_aodt_{tmp_suffix}.gml"
        usd_filename = f"map_aodt_{tmp_suffix}.usd"
        
        # 暫存 obj
        upload_dir = os.path.join(working_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        obj_path = os.path.join(upload_dir, obj_filename)
        
        # 輸出 gml/usd 路徑
        gml_out_dir = os.path.join(working_dir, "processed_gmls")
        usd_out_dir = os.path.join(working_dir, "processed_usds")
        os.makedirs(gml_out_dir, exist_ok=True)
        os.makedirs(usd_out_dir, exist_ok=True)
        
        gml_path = os.path.join(gml_out_dir, gml_filename)
        usd_path = os.path.join(usd_out_dir, usd_filename)
        
        logger.info(f"Saving uploaded OBJ to {obj_path}")
        file.save(obj_path)

        # 3.5 Validate OBJ content before conversion
        if not skip_obj_validation:
            try:
                validate_obj_required_objects(obj_path, required_objects)
            except OBJValidationError as ve:
                logger.warning(f"OBJ validation failed: {ve}")
                if not keep_files:
                    try:
                        os.remove(obj_path)
                    except Exception:
                        pass
                return jsonify({
                    "status": "error",
                    "message": "OBJ validation failed",
                    "missing": getattr(ve, 'missing', []),
                    "present": getattr(ve, 'present', []),
                    "required": getattr(ve, 'required', required_objects),
                    "hint": "請確認 OBJ 檔內有使用 'o <name>' 或 'g <name>' 宣告名稱，例如：o floor、o roof（或 g floor、g roof）。",
                    "details": str(ve),
                }), 400
        
        # 4. OBJ -> GML
        logger.info(f"Converting OBJ to GML with origin ({lat}, {lon}) -> EPSG:{epsg_gml}")
        converter = OBJToGMLConverter()
        converter.process(obj_path, gml_path, lat, lon, epsg_gml)

        # Optional: return GML for validation
        if output_format == 'gml':
            logger.info(f"Returning GML (skip USD conversion): {gml_path}")
            return_data = io.BytesIO()
            if os.path.exists(gml_path):
                with open(gml_path, 'rb') as fo:
                    return_data.write(fo.read())
                return_data.seek(0)

                if not keep_files:
                    try:
                        os.remove(obj_path)
                        os.remove(gml_path)
                    except Exception as e:
                        logger.warning(f"Cleanup failed: {e}")

                return send_file(
                    return_data,
                    mimetype='application/xml',
                    download_name=f"{response_base}.gml",
                )
            else:
                return jsonify({"status": "error", "message": "GML file not generated"}), 500
        
        # 5. GML -> USD
        logger.info(
            f"Converting GML to USD: {gml_path} -> {usd_path} (script={script_name}, "
            f"disable_interiors={disable_interiors})"
        )
        convert_citygml_to_usd(
            gml_path=gml_path,
            usd_path=usd_path,
            epsg_in=epsg_gml,
            epsg_out=epsg_usd,
            rough=True,
            script_name=script_name,
            disable_interiors=disable_interiors,
        )

        # 6. 回傳 USD
        return_data = io.BytesIO()
        if os.path.exists(usd_path):
            # Default: if output is not specified, return a bundle zip (USD + glTF assets)
            if output_format == '':
                bundle_dir = os.path.join(working_dir, "processed_bundles")
                os.makedirs(bundle_dir, exist_ok=True)

                tmp_gltf_dir = os.path.join(bundle_dir, f"{response_base}_gltf_{int(time.time())}")
                generated = usd_to_gltf_dir(usd_path, tmp_gltf_dir, base_name=response_base)

                bundle_zip_path = os.path.join(bundle_dir, f"{response_base}_bundle_{int(time.time())}.zip")
                files = [(f"{response_base}.usd", usd_path)]
                for f in generated:
                    files.append((os.path.basename(f), f))
                _zip_files(bundle_zip_path, files)

                with open(bundle_zip_path, 'rb') as fo:
                    return_data.write(fo.read())
                return_data.seek(0)

                if not keep_files:
                    try:
                        os.remove(obj_path)
                        os.remove(gml_path)
                        os.remove(usd_path)
                        for f in generated:
                            try:
                                os.remove(f)
                            except Exception:
                                pass
                        try:
                            os.rmdir(tmp_gltf_dir)
                        except Exception:
                            pass
                        os.remove(bundle_zip_path)
                    except Exception as e:
                        logger.warning(f"Cleanup failed: {e}")

                return send_file(return_data, mimetype='application/zip', download_name=f"{response_base}.zip")

            # Optional: USD -> GLB / glTF
            if output_format in {'glb', 'gltf', 'gltf_zip'}:
                gltf_out_dir = os.path.join(working_dir, "processed_gltfs")
                os.makedirs(gltf_out_dir, exist_ok=True)

                if output_format == 'glb':
                    glb_path = os.path.join(gltf_out_dir, f"{response_base}_{int(time.time())}.glb")
                    usd_to_glb(usd_path, glb_path)
                    with open(glb_path, 'rb') as fo:
                        return_data.write(fo.read())
                    return_data.seek(0)

                    if not keep_files:
                        try:
                            os.remove(obj_path)
                            os.remove(gml_path)
                            os.remove(usd_path)
                            os.remove(glb_path)
                        except Exception as e:
                            logger.warning(f"Cleanup failed: {e}")

                    return send_file(return_data, mimetype='model/gltf-binary', download_name=f"{response_base}.glb")

                if output_format == 'gltf':
                    gltf_path = os.path.join(gltf_out_dir, f"{response_base}_{int(time.time())}.gltf")
                    usd_to_gltf_single_file(usd_path, gltf_path, base_name=response_base)
                    with open(gltf_path, 'rb') as fo:
                        return_data.write(fo.read())
                    return_data.seek(0)

                    if not keep_files:
                        try:
                            os.remove(obj_path)
                            os.remove(gml_path)
                            os.remove(usd_path)
                            os.remove(gltf_path)
                        except Exception as e:
                            logger.warning(f"Cleanup failed: {e}")

                    return send_file(return_data, mimetype='model/gltf+json', download_name=f"{response_base}.gltf")

                zip_path = os.path.join(gltf_out_dir, f"{response_base}_gltf_{int(time.time())}.zip")
                usd_to_gltf_zip(usd_path, zip_path, base_name=response_base)
                with open(zip_path, 'rb') as fo:
                    return_data.write(fo.read())
                return_data.seek(0)

                if not keep_files:
                    try:
                        os.remove(obj_path)
                        os.remove(gml_path)
                        os.remove(usd_path)
                        os.remove(zip_path)
                    except Exception as e:
                        logger.warning(f"Cleanup failed: {e}")

                return send_file(return_data, mimetype='application/zip', download_name=f"{response_base}.zip")

            with open(usd_path,'rb') as fo:
                return_data.write(fo.read())
            return_data.seek(0)
            
            # 清理
            if not keep_files:
                try:
                    os.remove(obj_path)
                    os.remove(gml_path)
                    os.remove(usd_path)
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")

            return send_file(return_data, mimetype='application/octet-stream', download_name=f"{response_base}.usd")
        else:
             return jsonify({"status": "error", "message": "USD file not generated"}), 500

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"处理 process_obj 时发生错误: {str(e)}\n{error_trace}")
        return jsonify({
            "status": "error",
            "message": f"Server Error: {str(e)}",
            "stack_trace": error_trace
        }), 500

@app.route('/list_files', methods=['GET'])
def list_files():
    """列出已处理的GML文件"""
    try:
        processed_dir = "processed_gmls"
        if not os.path.exists(processed_dir):
            return jsonify({
                "status": "error",
                "message": f"目录 {processed_dir} 不存在"
            }), 404
            
        files = []
        for filename in os.listdir(processed_dir):
            file_path = os.path.join(processed_dir, filename)
            if os.path.isfile(file_path) and filename.endswith('.gml'):
                file_info = {
                    "name": filename,
                    "path": file_path,
                    "size": os.path.getsize(file_path),
                    "created": datetime.datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                }
                files.append(file_info)
                
        logger.info(f"列出文件: 找到 {len(files)} 个GML文件")
        return jsonify({
            "status": "success",
            "count": len(files),
            "files": files
        })
    
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"列出文件时发生错误: {str(e)}\n{error_trace}")
        return jsonify({
            "status": "error",
            "message": f"内部服务器错误: {str(e)}"
        }), 500

class StreamToLogger:
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level

    def write(self, message):
        message = message.strip()
        if message:
            self.logger.log(self.level, message)

    def flush(self):
        pass

# 將 print() 的輸出也導入 logging
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GML处理API服务')
    parser.add_argument('--port', type=int, default=5001, help='服务器端口号')
    parser.add_argument('--debug', action='store_true', help='是否启用调试模式')
    args = parser.parse_args()
    
    logger.info(f"启动GML处理API服务，端口: {args.port}, 调试模式: {args.debug}")
    app.run(host='0.0.0.0', port=args.port, debug=args.debug) 