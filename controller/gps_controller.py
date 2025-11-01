from flask import Blueprint, jsonify, request
from flask_socketio import emit
from model.gps_model import GPSData
import logging
from socket_instance import socketio

logger = logging.getLogger(__name__)

gps_blueprint = Blueprint('gps', __name__)

# Lưu trữ dữ liệu GPS của các thiết bị
gps_data_store = {}

@socketio.on('connect')
def handle_connect():
    logger.info(f"[GPS] Client connected - SID: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"[GPS] Client disconnected - SID: {request.sid}")

@socketio.on('gps_data')
def handle_gps_data(data):
    try:
        gps_data = GPSData.from_dict(data)
        gps_data_store[gps_data.device_id] = gps_data.to_dict()  
        # Gửi dữ liệu đến tất cả clients
        emit('gps_update', gps_data.to_dict(), broadcast=True)
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"[GPS] Error processing GPS data: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}