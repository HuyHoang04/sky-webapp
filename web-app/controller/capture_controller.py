"""
Capture Controller - Handle image capture via Socket.IO
"""
import logging
from datetime import datetime
from flask import Blueprint, request
from socket_instance import socketio
from flask_socketio import emit
from database import SessionLocal
from model.capture_model import CaptureRecord

logger = logging.getLogger(__name__)

# Create blueprint
capture_blueprint = Blueprint('capture', __name__)


# ============================================
# SOCKET.IO HANDLERS
# ============================================

@socketio.on('capture_request')
def handle_capture_request(data):
    """
    Handle capture request from dashboard/frontend
    Forward command to drone device via Socket.IO
    """
    try:
        device_id = data.get('device_id', 'drone-camera')
        
        logger.info(f"[WEBAPP] 📸 Received capture_request from frontend")
        logger.info(f"[WEBAPP] 📸 Data: {data}")
        logger.info(f"[WEBAPP] 📸 Target device_id: {device_id}")
        
        # Forward capture command to specific drone device room
        command_data = {
            'device_id': device_id,
            'timestamp': data.get('timestamp'),
            'quality': 95
        }
        logger.info(f"[WEBAPP] 📤 Emitting capture_command to room '{device_id}' with data: {command_data}")
        
        socketio.emit('capture_command', command_data, to=device_id)
        
        logger.info(f"[WEBAPP] ✅ Capture command emitted to room: {device_id}")
        
    except Exception as e:
        logger.error(f"[CAPTURE] ❌ Error handling capture request: {str(e)}")
        emit('capture_error', {'error': str(e)})


@socketio.on('capture_result')
def handle_capture_result(data):
    """
    Handle capture result from drone
    Drone sends: image_url, gps_data, timestamp
    """
    try:
        device_id = data.get('device_id')
        success = data.get('success', False)
        
        logger.info(f"[CAPTURE] 📥 Received capture result from {device_id}, success: {success}")
        
        if not success:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"[CAPTURE] ❌ Capture failed: {error_msg}")
            emit('capture_error', {'device_id': device_id, 'error': error_msg}, broadcast=True)
            return
        
        # Extract data
        image_url = data.get('image_url')
        gps_data = data.get('gps_data', {})
        timestamp = data.get('timestamp')
        
        logger.info(f"[CAPTURE] 📸 Image URL: {image_url}")
        logger.info(f"[CAPTURE] 📍 GPS: {gps_data}")
        
        # Save to database
        db = SessionLocal()
        try:
            capture_record = CaptureRecord(
                device_id=device_id,
                original_image_url=image_url,
                latitude=gps_data.get('latitude') if gps_data else None,
                longitude=gps_data.get('longitude') if gps_data else None,
                altitude=gps_data.get('altitude') if gps_data else None,
                analysis_status='pending',
                created_at=datetime.fromisoformat(timestamp) if timestamp else datetime.now()
            )
            
            db.add(capture_record)
            db.commit()
            db.refresh(capture_record)
            
            logger.info(f"[CAPTURE] 💾 Saved to database with ID: {capture_record.id}")
            
            # TODO: Trigger AI analysis in background (Bước 4)
            # Will add background thread to send to AI service and update record
            
        except Exception as db_error:
            logger.error(f"[CAPTURE] ❌ Database error: {str(db_error)}")
            db.rollback()
            emit('capture_error', {'device_id': device_id, 'error': f'Database save failed: {str(db_error)}'}, broadcast=True)
            return
        finally:
            db.close()
        
        # Notify frontend that capture was successful
        emit('capture_success', {
            'device_id': device_id,
            'capture_id': capture_record.id,
            'image_url': image_url,
            'gps_data': gps_data,
            'timestamp': timestamp
        }, broadcast=True)
        
        logger.info(f"[CAPTURE] ✅ Capture processed and saved successfully")
        
    except Exception as e:
        logger.error(f"[CAPTURE] ❌ Error handling capture result: {str(e)}")
        emit('capture_error', {'error': str(e)}, broadcast=True)
