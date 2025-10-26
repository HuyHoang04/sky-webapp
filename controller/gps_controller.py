from flask import Blueprint, jsonify, request
from flask_socketio import emit
from model.gps_model import GPSData
import json
from socket_instance import socketio

gps_blueprint = Blueprint('gps', __name__)

# Lưu trữ dữ liệu GPS của các thiết bị
gps_data_store = {}

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """
    Xử lý khi client ngắt kết nối WebSocket
    """
    print('Client disconnected')

@socketio.on('gps_data')
def handle_gps_data(data):
    """
    Nhận dữ liệu GPS từ thiết bị và gửi đến tất cả clients
    """
    try:
        gps_data = GPSData.from_dict(data)
        gps_data_store[gps_data.device_id] = gps_data.to_dict()
        
        # Gửi dữ liệu đến tất cả clients
        emit('gps_update', gps_data.to_dict(), broadcast=True)
        return {'status': 'success'}
    except Exception as e:
        print(f"Error processing GPS data: {e}")
        return {'status': 'error', 'message': str(e)}

@gps_blueprint.route('/api/gps', methods=['GET'])
def get_all_gps_data():
    """
    API endpoint để lấy tất cả dữ liệu GPS hiện tại
    """
    return jsonify(gps_data_store)

@gps_blueprint.route('/api/gps/<device_id>', methods=['GET'])
def get_device_gps_data(device_id):
    """
    API endpoint để lấy dữ liệu GPS của một thiết bị cụ thể
    """
    if device_id in gps_data_store:
        return jsonify(gps_data_store[device_id])
    return jsonify({'error': 'Device not found'}), 404

@gps_blueprint.route('/api/gps', methods=['POST'])
def receive_gps_data():
    """
    API endpoint để nhận dữ liệu GPS từ thiết bị qua HTTP
    """
    try:
        data = request.json
        gps_data = GPSData.from_dict(data)
        gps_data_store[gps_data.device_id] = gps_data.to_dict()
        
        # Gửi dữ liệu qua WebSocket
        socketio.emit('gps_update', gps_data.to_dict())
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400