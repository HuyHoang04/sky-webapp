from flask_socketio import emit
from typing import Dict, Any
import json

class WebRTCUtils:
    def __init__(self):
        self._device_id = None
        self._device_name = None
        self._current_call = None

    def emit_call_state(self, state: Dict[str, Any]):
        """Gửi trạng thái cuộc gọi đến dashboard"""
        if self._device_id:
            emit('call_state', {
                'device_id': self._device_id,
                'device_name': self._device_name,
                **state
            }, broadcast=True)

    def handle_incoming_call(self, phone_number: str):
        """Xử lý khi có cuộc gọi đến"""
        self._current_call = {
            'phoneNumber': phone_number,
            'status': 'ringing'
        }
        self.emit_call_state({
            'type': 'incoming_call',
            'phoneNumber': phone_number
        })

    def handle_call_connected(self):
        """Xử lý khi cuộc gọi được kết nối"""
        if self._current_call:
            self._current_call['status'] = 'connected'
            self.emit_call_state({
                'type': 'call_connected'
            })

    def handle_call_ended(self):
        """Xử lý khi cuộc gọi kết thúc"""
        if self._current_call:
            self.emit_call_state({
                'type': 'call_ended'
            })
            self._current_call = None

    def handle_gps_update(self, gps_data: Dict[str, Any]):
        """Gửi dữ liệu GPS trong cuộc gọi"""
        if self._current_call:
            self.emit_call_state({
                'type': 'location_update',
                'latitude': gps_data.get('latitude'),
                'longitude': gps_data.get('longitude'),
                'altitude': gps_data.get('altitude'),
                'speed': gps_data.get('speed'),
                'timestamp': gps_data.get('timestamp')
            })