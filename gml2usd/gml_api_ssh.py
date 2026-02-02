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
from obj_converter import OBJToGMLConverter
import requests

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

        #設定local的usd位置
        usd_name = gml_name.split(".gml")[0] + ".usd"
        working_file = os.path.abspath(__file__)
        working_dir = os.path.dirname(working_file)
        usd_path = os.path.join(working_dir,f"processed_usds/{usd_name}")
   

        # 记录请求信息
        logger.info(
            f"收到处理请求: lat={lat}, lon={lon}, margin={margin}, gml_name={gml_name}, "
            f"disable_interiors={disable_interiors}"
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

        #return files and delete the files
        return_data = io.BytesIO()
        with open(usd_path,'rb') as fo:
            return_data.write(fo.read())
        return_data.seek(0)
        os.remove(usd_path)
        os.remove(gml_path)
        return send_file(return_data,mimetype='application/octet-stream')
    
    except Exception as e:
        # 记录异常堆栈
        error_trace = traceback.format_exc()
        logger.error(f"处理请求时发生错误: {str(e)}\n{error_trace}")
        return jsonify({
            "status": "error",
            "message": f"内部服务器错误: {str(e)}",
            "stack_trace": error_trace
        }), 500
    
@app.route('/to_usd',methods=['POST'])
def to_usd():
    """給gml處理成usd"""
    logger.info("receive request")
    try:
        if 'epsg_in' not in request.form:
            return jsonify({
                "status": "error",
                "message": "no epsg_in"
            }), 400
        if 'gml_file' not in request.files:
            return jsonify({
                "status": "error",
                "message": "no gml"
            }), 400
        gml_file = request.files['gml_file']
        if gml_file.filename == '':
            return jsonify({
                "status": "error",
                "message": "empty file"
            }),400
        epsg_in = request.form['epsg_in']
        epsg_out = request.form.get('epsg_out', '32654')
        disable_interiors = _parse_bool(request.form.get('disable_interiors', None), default=False)
        
        if 'project_id' not in request.form:
            return jsonify({
                "status": "error",
                "message": "no project_id"
            }),400
        project_id = request.form['project_id']
        #定gml_path
        default_gml_name = f"map_aodt_{project_id}.gml"
        gml_path = os.path.join("processed_gmls",default_gml_name)

        gml_file.save(gml_path)
        #定usd_path
        working_file = os.path.abspath(__file__)
        working_dir = os.path.dirname(working_file)
        default_usd_name = os.path.splitext(default_gml_name)[0] + '.usd'
        usd_path = os.path.join(working_dir,f"processed_usds/{default_usd_name}")
        logger.info(
            f"start converting (local), gml_path: {gml_path} , usd_path: {usd_path}, "
            f"disable_interiors={disable_interiors}"
        )
        try:
            convert_citygml_to_usd(
                gml_path=gml_path,
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
            }), 500

        return_data = io.BytesIO()
        with open(usd_path,'rb') as fo:
            return_data.write(fo.read())
        return_data.seek(0)
        os.remove(usd_path)
        os.remove(gml_path)
        return send_file(return_data,mimetype='application/octet-stream')

    except Exception as e:
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
        # Converter script inside /opt/aodt_ui_gis
        # Default: indoor + groundplane + domain pipeline.
        script_name = (
            request.form.get('script_name', 'citygml2aodt_indoor_groundplane_domain.py')
            or 'citygml2aodt_indoor_groundplane_domain.py'
        ).strip()
        output_format = (request.form.get('output', 'usd') or 'usd').strip().lower()
        keep_files = (request.form.get('keep_files', '0') or '0').strip() == '1'
        
        if not lat_str or not lon_str:
             return jsonify({"status": "error", "message": "Missing lat or lon parameters"}), 400
             
        lat = float(lat_str)
        lon = float(lon_str)

        # 3. 準備路徑
        working_file = os.path.abspath(__file__)
        working_dir = os.path.dirname(working_file)
        
        obj_filename = f"{project_id}.obj"
        gml_filename = f"map_aodt_{project_id}.gml"
        usd_filename = f"map_aodt_{project_id}.usd"
        
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
                    download_name=gml_filename,
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

            return send_file(return_data, mimetype='application/octet-stream', download_name=usd_filename)
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