from flask import Blueprint, jsonify, request, render_template
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
async def handle_webrtc_offer(data):
    """
    Xử lý WebRTC offer từ client
    """
    device_id = data['device_id']
    offer = RTCSessionDescription(sdp=data['sdp'], type=data['type'])
    
    # Tạo peer connection mới
    pc = RTCPeerConnection()
    peer_connections[device_id] = pc
    
    # Thiết lập các event handlers
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state for {device_id}: {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            del peer_connections[device_id]
    
    # Xử lý offer và tạo answer
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    # Gửi answer về client
    emit('webrtc_answer', {
        'device_id': device_id,
        'sdp': pc.localDescription.sdp,
        'type': pc.localDescription.type
    })

@socketio.on('webrtc_ice_candidate')
async def handle_ice_candidate(data):
    """
    Xử lý ICE candidate từ client
    """
    device_id = data['device_id']
    if device_id in peer_connections:
        candidate = RTCIceCandidate(
            sdpMid=data['candidate'].get('sdpMid'),
            sdpMLineIndex=data['candidate'].get('sdpMLineIndex'),
            candidate=data['candidate'].get('candidate')
        )
        await peer_connections[device_id].addIceCandidate(candidate)

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