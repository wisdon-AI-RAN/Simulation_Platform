from flask import Blueprint, jsonify
import os

test_bp = Blueprint('test', __name__)

@test_bp.route('/test', methods=['GET'])
def test_route():
    return jsonify({"status": "success", "message": "This is a test route!!!"})