from flask import Blueprint, jsonify
from socket_instance import socketio
import datetime

call_blueprint = Blueprint('call', __name__)

# Lưu trữ thông tin cuộc gọi
active_calls = {}
call_history = []

@socketio.on('incoming_call')
def handle_incoming_call(data):
    """Xử lý khi có cuộc gọi đến từ SIM"""
    call_id = data.get('id')
    phone_number = data.get('phoneNumber')
    
    # Lưu thông tin cuộc gọi
    active_calls[call_id] = {
        'id': call_id,
        'phoneNumber': phone_number,
        'startTime': datetime.datetime.now(),
        'status': 'ringing',
        'note': '',
        'location': None
    }
    
    # Gửi thông báo có cuộc gọi đến cho client
    socketio.emit('incoming_call', {
        'id': call_id,
        'phoneNumber': phone_number
    })

@socketio.on('accept_call')
def handle_accept_call(data):
    """Xử lý khi người dùng chấp nhận cuộc gọi"""
    call_id = data.get('callId')
    if call_id in active_calls:
        active_calls[call_id]['status'] = 'active'
        active_calls[call_id]['acceptTime'] = datetime.datetime.now()
        
        # Gửi lệnh accept đến SIM
        socketio.emit('sim_accept_call', {'callId': call_id})

@socketio.on('decline_call')
def handle_decline_call(data):
    """Xử lý khi người dùng từ chối cuộc gọi"""
    call_id = data.get('callId')
    if call_id in active_calls:
        call_info = active_calls.pop(call_id)
        call_info['endTime'] = datetime.datetime.now()
        call_info['status'] = 'declined'
        call_history.append(call_info)
        
        # Gửi lệnh decline đến SIM
        socketio.emit('sim_decline_call', {'callId': call_id})

@socketio.on('end_call')
def handle_end_call(data):
    """Xử lý khi người dùng kết thúc cuộc gọi"""
    call_id = data.get('callId')
    note = data.get('note', '')
    duration = data.get('duration', 0)
    
    if call_id in active_calls:
        call_info = active_calls.pop(call_id)
        call_info['endTime'] = datetime.datetime.now()
        call_info['status'] = 'ended'
        call_info['note'] = note
        call_info['duration'] = duration
        call_history.append(call_info)
        
        # Gửi lệnh end đến SIM
        socketio.emit('sim_end_call', {'callId': call_id})

@socketio.on('sim_location_update')
def handle_sim_location(data):
    """Xử lý khi nhận được cập nhật vị trí từ SIM"""
    call_id = data.get('callId')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    
    if call_id in active_calls:
        active_calls[call_id]['location'] = {
            'latitude': latitude,
            'longitude': longitude,
            'timestamp': datetime.datetime.now()
        }
        
        # Gửi thông tin vị trí cho client
        socketio.emit('call_location_update', {
            'callId': call_id,
            'latitude': latitude,
            'longitude': longitude
        })

@call_blueprint.route('/api/calls/history', methods=['GET'])
def get_call_history():
    """API endpoint để lấy lịch sử cuộc gọi"""
    return jsonify([{
        'id': call['id'],
        'phoneNumber': call['phoneNumber'],
        'startTime': call['startTime'].isoformat(),
        'endTime': call['endTime'].isoformat() if 'endTime' in call else None,
        'status': call['status'],
        'duration': call.get('duration', 0),
        'note': call.get('note', ''),
        'location': call.get('location')
    } for call in call_history])