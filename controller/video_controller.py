from flask import Blueprint, jsonify, request, render_template
from flask_socketio import emit
from model.video_model import VideoStream
import logging
from socket_instance import socketio

logger = logging.getLogger(__name__)

video_blueprint = Blueprint('video', __name__)

# Lưu trữ thông tin về các video streams
video_streams = {}

@video_blueprint.route('/api/video/streams', methods=['GET'])
def get_all_streams():
    logger.info(f"[VIDEO API] GET all video streams - Count: {len(video_streams)}")
    return jsonify({id: stream.to_dict() for id, stream in video_streams.items()})

@video_blueprint.route('/api/video/stream/<device_id>', methods=['GET'])
def get_stream(device_id):
    logger.info(f"[VIDEO API] GET video stream for device: {device_id}")
    if device_id in video_streams:
        return jsonify(video_streams[device_id].to_dict())
    logger.warning(f"[VIDEO API] Stream not found for device: {device_id}")
    return jsonify({'error': 'Stream not found'}), 404

@video_blueprint.route('/webrtc/<device_id>', methods=['GET'])
def webrtc_view(device_id):
    """
    Trang xem video WebRTC cho một thiết bị cụ thể
    """
    logger.info(f"[VIDEO] Rendering WebRTC view for device: {device_id}")
    return render_template('webrtc.html', device_id=device_id)

@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    """
    Xử lý WebRTC offer từ drone client
    """
    device_id = data['device_id']
    logger.info(f"[WEBRTC] Received webrtc_offer from drone: {device_id}")
    logger.debug(f"[WEBRTC] Offer SDP type: {data.get('type')}")
    
    # Forward offer đến tất cả clients frontend
    emit('webrtc_offer', data, broadcast=True, skip_sid=request.sid)
    logger.info(f"[WEBRTC] Forwarded offer from drone {device_id} to frontend clients")


@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    """
    Xử lý answer từ frontend
    """
    device_id = data['device_id']
    logger.info(f"[WEBRTC] Received webrtc_answer from frontend for drone: {device_id}")
    logger.debug(f"[WEBRTC] Answer SDP type: {data.get('type')}")
    
    # Forward answer đến drone
    emit('webrtc_answer', data, broadcast=True, skip_sid=request.sid)
    logger.info(f"[WEBRTC] Forwarded answer to drone: {device_id}")

@socketio.on('start_webrtc')
def handle_start_webrtc(data):
    """
    Xử lý yêu cầu bắt đầu WebRTC từ frontend
    """
    device_id = data['device_id']
    logger.info(f"[WEBRTC] Received start_webrtc request for drone: {device_id}")
    
    # Chuyển tiếp yêu cầu đến drone
    emit('start_webrtc', data, broadcast=True, skip_sid=request.sid)
    logger.info(f"[WEBRTC] Forwarded start_webrtc request to drone: {device_id}")
    
@socketio.on('webrtc_ice_candidate')
def handle_webrtc_ice_candidate(data):
    """
    Xử lý ICE candidate từ drone hoặc frontend
    """
    device_id = data['device_id']
    logger.info(f"[WEBRTC] Received ICE candidate for device: {device_id}")
    logger.debug(f"[WEBRTC] ICE candidate: {data.get('candidate', {}).get('candidate', 'N/A')[:50]}...")
    
    # Forward ICE candidate đến các clients khác
    emit('webrtc_ice_candidate', data, broadcast=True, skip_sid=request.sid)
    logger.info(f"[WEBRTC] Forwarded ICE candidate for device: {device_id}")

@socketio.on('webrtc_status')
def handle_webrtc_status(data):
    """
    Xử lý cập nhật trạng thái WebRTC từ drone hoặc frontend
    """
    device_id = data.get('device_id')
    status = data.get('status')
    logger.info(f"[WEBRTC] Received WebRTC status from device {device_id}: {status}")
    
    # Forward trạng thái đến các clients khác
    emit('webrtc_status', data, broadcast=True, skip_sid=request.sid)
    logger.info(f"[WEBRTC] Forwarded WebRTC status for device: {device_id}")

@socketio.on('register_video_device')
def register_video_device(data):
    """
    Đăng ký thiết bị video mới
    """
    try:
        device_id = data['device_id']
        logger.info(f"[VIDEO] Registering video device: {device_id}")
        logger.debug(f"[VIDEO] Device data: {data}")
        
        stream = VideoStream(
            device_id=device_id,
            stream_url=data.get('stream_url'),
            webrtc_config=data.get('webrtc_config')
        )
        stream.is_active = True
        video_streams[device_id] = stream
        logger.info(f"[VIDEO] Device {device_id} registered successfully")
        
        # Thông báo cho tất cả clients về thiết bị mới
        emit('video_device_added', stream.to_dict(), broadcast=True)
        logger.info(f"[VIDEO] Broadcasted video_device_added for: {device_id}")
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"[VIDEO] Error registering video device: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}