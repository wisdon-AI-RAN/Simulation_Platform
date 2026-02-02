from flask import Blueprint, jsonify
from utils.ssh_utils import execute_remote_script
import os

SSH_HOST = os.getenv('SSH_HOST')
SSH_PORT = os.getenv('SSH_PORT')
SSH_USER = os.getenv('SSH_USER')
SSH_PASSWORD = os.getenv('SSH_PASSWORD')
START_SCRIPT = os.getenv('START_SCRIPT')

aodt_restart_bp = Blueprint('aodt_restart', __name__)

@aodt_restart_bp.route('/restart', methods=['POST'])
def restart_aodt():
    result = execute_remote_script(
        ssh_host=SSH_HOST,
        ssh_port=SSH_PORT,
        ssh_user=SSH_USER,
        password=SSH_PASSWORD,
        script_path=START_SCRIPT
    )
    if result.get("status") == "success":
        return jsonify({"status": "success", "output": result.get("output", "Successfully restarted AODT.")}), 200
    
    return jsonify({"status": "error", "error": result.get("error"), "code": result.get("code")}), 500