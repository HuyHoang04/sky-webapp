from flask import Blueprint, jsonify, request
from flask_socketio import emit, join_room
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

@socketio.on('device_register')
def handle_device_register(data):
    """Register device and join its room for targeted communication"""
    try:
        device_id = data.get('device_id')
        if device_id:
            join_room(device_id)
            logger.info(f"[DEVICE] {device_id} registered and joined room")
            emit('device_registered', {'device_id': device_id, 'status': 'success'})
        else:
            logger.warning(f"[DEVICE] Registration failed - no device_id")
            emit('device_registered', {'status': 'error', 'message': 'Missing device_id'})
    except Exception as e:
        logger.error(f"[DEVICE] Error registering device: {e}")
        emit('device_registered', {'status': 'error', 'message': str(e)})

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


@gps_blueprint.route('/api/gps', methods=['GET'])
def get_all_gps_data():
    """Return current GPS data store as JSON for dashboard consumption"""
    try:
        return jsonify(gps_data_store)
    except Exception as e:
        logger.error(f"[GPS API] Error returning gps data: {e}", exc_info=True)
        return jsonify({'error': 'Failed to retrieve GPS data'}), 500