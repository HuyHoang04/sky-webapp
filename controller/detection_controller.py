from flask import Blueprint, jsonify, request
from flask_socketio import emit
from model.detection_model import DetectionData, DetectionReport
import logging
from socket_instance import socketio
from datetime import datetime
import os
import base64

logger = logging.getLogger(__name__)

detection_blueprint = Blueprint('detection', __name__)

# Store latest detection data from devices
detection_data_store = {}

# Store detection history for reports
detection_history = []

@socketio.on('detection_data')
def handle_detection_data(data):
    """Handle incoming detection data from drone"""
    try:
        detection = DetectionData.from_dict(data)
        device_id = detection.device_id
        
        # Store latest detection data
        detection_data_store[device_id] = detection.to_dict()
        
        # Add to history
        detection_history.append(detection.to_dict())
        
        # Keep only last 1000 entries
        if len(detection_history) > 1000:
            detection_history.pop(0)
        
        # Broadcast to all connected web clients
        emit('detection_update', detection.to_dict(), broadcast=True)
        
        logger.info(f"[DETECTION] Device {device_id}: Earth={detection.earth_person}, Sea={detection.sea_person}, Total={detection.total}")
        
        return {'status': 'success'}
    except Exception as e:
        logger.error(f"[DETECTION] Error processing detection data: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

@socketio.on('detection_snapshot')
def handle_detection_snapshot(data):
    """Handle incoming detection snapshot with image"""
    try:
        device_id = data.get('device_id')
        image_data = data.get('image')  # Base64 encoded image
        detection_data = data.get('detection_data')
        
        if not device_id or not image_data or not detection_data:
            return {'status': 'error', 'message': 'Missing required fields'}
        
        # Save snapshot to database
        snapshot = DetectionReport(
            device_id=device_id,
            device_name=data.get('device_name', 'Unknown'),
            earth_person_count=detection_data.get('earth_person', 0),
            sea_person_count=detection_data.get('sea_person', 0),
            total_count=detection_data.get('total', 0),
            image_data=image_data,
            timestamp=datetime.now()
        )
        
        snapshot.save()
        
        logger.info(f"[DETECTION] Saved snapshot for device {device_id}")
        
        # Broadcast snapshot saved event
        emit('snapshot_saved', {
            'device_id': device_id,
            'timestamp': snapshot.timestamp.isoformat(),
            'total_count': snapshot.total_count
        }, broadcast=True)
        
        return {'status': 'success', 'snapshot_id': snapshot.id}
    except Exception as e:
        logger.error(f"[DETECTION] Error saving snapshot: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

@detection_blueprint.route('/api/detection/latest')
def get_latest_detections():
    """Get latest detection data from all devices"""
    return jsonify(detection_data_store)

@detection_blueprint.route('/api/detection/history')
def get_detection_history():
    """Get detection history"""
    limit = request.args.get('limit', 100, type=int)
    return jsonify(detection_history[-limit:])

@detection_blueprint.route('/api/detection/reports')
def get_detection_reports():
    """Get saved detection reports from database"""
    try:
        limit = request.args.get('limit', 50, type=int)
        device_id = request.args.get('device_id', None)
        
        reports = DetectionReport.get_recent_reports(limit=limit, device_id=device_id)
        
        return jsonify({
            'status': 'success',
            'count': len(reports),
            'reports': [report.to_dict() for report in reports]
        })
    except Exception as e:
        logger.error(f"Error getting detection reports: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@detection_blueprint.route('/api/detection/report/<int:report_id>')
def get_detection_report(report_id):
    """Get specific detection report with image"""
    try:
        report = DetectionReport.get_by_id(report_id)
        if not report:
            return jsonify({'status': 'error', 'message': 'Report not found'}), 404
        
        return jsonify({
            'status': 'success',
            'report': report.to_dict(include_image=True)
        })
    except Exception as e:
        logger.error(f"Error getting detection report: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@detection_blueprint.route('/api/detection/stats')
def get_detection_stats():
    """Get detection statistics"""
    try:
        stats = DetectionReport.get_statistics()
        return jsonify({
            'status': 'success',
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting detection stats: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
