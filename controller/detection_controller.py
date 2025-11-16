from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
from socket_instance import socketio
import logging

logger = logging.getLogger(__name__)

detection_blueprint = Blueprint('detection', __name__)

# Socket.IO event handler for detection results from drone
@socketio.on('detection_result')
def handle_detection_result(data):
    """Handle detection result from drone and broadcast to clients"""
    try:
        device_id = data.get('device_id')
        earth_count = data.get('earth_person_count', 0)
        sea_count = data.get('sea_person_count', 0)
        total_count = data.get('person_count', 0)
        
        logger.info(f"Detection from {device_id}: earth={earth_count}, sea={sea_count}, total={total_count}")
        
        # Broadcast to all connected clients
        socketio.emit('detection_update', {
            'device_id': device_id,
            'earth_person_count': earth_count,
            'sea_person_count': sea_count,
            'person_count': total_count,
            'timestamp': data.get('timestamp'),
            'detections': data.get('detections', []),
            'gps': data.get('gps')
        })
        
    except Exception as e:
        logger.error(f"Error handling detection result: {e}")

@detection_blueprint.route('/detection')
def detection_page():
    return render_template('detection.html')

@detection_blueprint.route('/api/items', methods=['GET', 'POST'])
def handle_items():
    if request.method == 'POST':
        item_data = request.json
        # TODO: Save item to database
        return jsonify({'status': 'success', 'message': 'Item added successfully'})
    else:
        # TODO: Get items from database
        return jsonify([])

@detection_blueprint.route('/api/analyze', methods=['POST'])
def analyze_items():
    items = request.json.get('items', [])
    # TODO: Implement AI analysis
    return jsonify({
        'status': 'success',
        'detections': [],
        'recordings': []
    })

@detection_blueprint.route('/api/detections', methods=['GET'])
def get_detections():
    # TODO: Get detections from database
    return jsonify([]) # SAI -> Hiển thị hình ảnh từ cloudinary gửi về 

# Đẩy ảnh cho server có AI -> đẩy cho cloudinary -> trả về ảnh đã bounding box cho frontend hiển thị

@detection_blueprint.route('/api/recordings', methods=['GET'])
def get_recordings():
    # TODO: Get recordings from database
    return jsonify([])

@detection_blueprint.route('/api/export', methods=['POST'])
def export_results():
    data = request.json
    # TODO: Generate export file
    return jsonify({
        'status': 'success',
        'url': '/exports/analysis_report.pdf'
    })