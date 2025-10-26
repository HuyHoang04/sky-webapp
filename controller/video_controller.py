from flask import Blueprint, jsonify, request, render_template
from flask_socketio import emit
from model.video_model import VideoStream
import json
from socket_instance import socketio
import asyncio
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCIceCandidate

video_blueprint = Blueprint('video', __name__)

# Lưu trữ thông tin về các video streams
video_streams = {}
# Lưu trữ các kết nối WebRTC
peer_connections = {}
# Lưu trữ các offer từ drone clients
pending_offers = {}

class VideoStreamTrack(MediaStreamTrack):
    """
    Lớp xử lý video track cho WebRTC
    """
    kind = "video"
    
    def __init__(self, track):
        super().__init__()
        self.track = track
    
    async def recv(self):
        frame = await self.track.recv()
        return frame

@video_blueprint.route('/api/video/streams', methods=['GET'])
def get_all_streams():
    """
    API endpoint để lấy thông tin về tất cả các video streams
    """
    return jsonify({id: stream.to_dict() for id, stream in video_streams.items()})

@video_blueprint.route('/api/video/stream/<device_id>', methods=['GET'])
def get_stream(device_id):
    """
    API endpoint để lấy thông tin về một video stream cụ thể
    """
    if device_id in video_streams:
        return jsonify(video_streams[device_id].to_dict())
    return jsonify({'error': 'Stream not found'}), 404

@video_blueprint.route('/webrtc/<device_id>', methods=['GET'])
def webrtc_view(device_id):
    """
    Trang xem video WebRTC cho một thiết bị cụ thể
    """
    return render_template('webrtc.html', device_id=device_id)

@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    """
    Xử lý WebRTC offer từ drone client
    """
    device_id = data['device_id']
    logging.info(f"Nhận webrtc_offer từ drone: {device_id}")
    
    # Forward offer đến tất cả clients frontend
    emit('webrtc_offer', data, broadcast=True, skip_sid=request.sid)
    logging.info(f"Đã chuyển tiếp offer từ drone {device_id} đến frontend")


@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    """
    Xử lý answer từ frontend
    """
    device_id = data['device_id']
    logging.info(f"Nhận webrtc_answer từ frontend cho drone: {device_id}")
    
    # Forward answer đến drone
    emit('webrtc_answer', data, broadcast=True, skip_sid=request.sid)
    logging.info(f"Đã chuyển tiếp answer đến drone: {device_id}")

@socketio.on('start_webrtc')
def handle_start_webrtc(data):
    """
    Xử lý yêu cầu bắt đầu WebRTC từ frontend
    """
    device_id = data['device_id']
    logging.info(f"Nhận yêu cầu bắt đầu WebRTC cho drone: {device_id}")
    
    # Chuyển tiếp yêu cầu đến drone
    emit('start_webrtc', data, broadcast=True, skip_sid=request.sid)
    logging.info(f"Đã chuyển tiếp yêu cầu bắt đầu WebRTC đến drone: {device_id}")
    
@socketio.on('webrtc_ice_candidate')
def handle_webrtc_ice_candidate(data):
    """
    Xử lý ICE candidate từ drone hoặc frontend
    """
    device_id = data['device_id']
    logging.info(f"Nhận ICE candidate cho thiết bị: {device_id}")
    
    # Forward ICE candidate đến các clients khác
    emit('webrtc_ice_candidate', data, broadcast=True, skip_sid=request.sid)
    logging.info(f"Đã chuyển tiếp ICE candidate cho thiết bị: {device_id}")

@socketio.on('webrtc_status')
def handle_webrtc_status(data):
    """
    Xử lý cập nhật trạng thái WebRTC từ drone hoặc frontend
    """
    device_id = data.get('device_id')
    status = data.get('status')
    logging.info(f"Nhận trạng thái WebRTC từ thiết bị {device_id}: {status}")
    
    # Forward trạng thái đến các clients khác
    emit('webrtc_status', data, broadcast=True, skip_sid=request.sid)
            
            
            
            
            
                
                
            

            
    
    


@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    """
    Xử lý answer từ drone hoặc frontend
    """
    device_id = data['device_id']
    print(f"Received webrtc_answer for device: {device_id}")
    
    # Forward answer đến tất cả clients khác
    emit('webrtc_answer', data, broadcast=True, skip_sid=request.sid)


@socketio.on('webrtc_ice_candidate')
def handle_ice_candidate(data):
    """
    Xử lý ICE candidate từ client
    """
    device_id = data['device_id']
    print(f"Forwarding ICE candidate for device: {device_id}")
    
    def add_candidate():
        import asyncio
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if device_id in peer_connections:
                candidate = RTCIceCandidate(
                    sdpMid=data['candidate'].get('sdpMid'),
                    sdpMLineIndex=data['candidate'].get('sdpMLineIndex'),
                    candidate=data['candidate'].get('candidate')
                )
                loop.run_until_complete(peer_connections[device_id].addIceCandidate(candidate))
        except Exception as e:
            print(f"Error adding ICE candidate: {e}")
        finally:
            loop.close()
    
    import threading
    thread = threading.Thread(target=add_candidate)
    thread.daemon = True
    thread.start()
    emit('webrtc_ice_candidate', data, broadcast=True, skip_sid=request.sid)

@socketio.on('register_video_device')
def register_video_device(data):
    """
    Đăng ký thiết bị video mới
    """
    try:
        device_id = data['device_id']
        stream = VideoStream(
            device_id=device_id,
            stream_url=data.get('stream_url'),
            webrtc_config=data.get('webrtc_config')
        )
        stream.is_active = True
        video_streams[device_id] = stream
        
        # Thông báo cho tất cả clients về thiết bị mới
        emit('video_device_added', stream.to_dict(), broadcast=True)
        return {'status': 'success'}
    except Exception as e:
        print(f"Error registering video device: {e}")
        return {'status': 'error', 'message': str(e)}