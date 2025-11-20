"""
Capture Controller - Handle image capture via Socket.IO
"""
import logging
import os
import threading
import requests
from datetime import datetime
from flask import Blueprint, request
from socket_instance import socketio
from flask_socketio import emit
from database import SessionLocal
from model.capture_model import CaptureRecord
from controller.gps_controller import gps_data_store

logger = logging.getLogger(__name__)

# AI Service configuration
AI_SERVICE_URL = os.getenv('AI_IMAGE_SERVICE_URL', 'http://localhost:8000')

# Create blueprint
capture_blueprint = Blueprint('capture', __name__)

logger.info("=" * 60)
logger.info("🎯 CAPTURE CONTROLLER LOADED")
logger.info("=" * 60)


# ============================================
# SOCKET.IO HANDLERS
# ============================================

@socketio.on('capture_request')
def handle_capture_request(data):
    """
    Handle capture request from dashboard/frontend
    Forward command to drone device via Socket.IO
    """
    logger.warning("=" * 80)
    logger.warning("🚨 CAPTURE_REQUEST HANDLER CALLED!")
    logger.warning("=" * 80)
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
        logger.info(f"[WEBAPP]  Emitting capture_command to room '{device_id}' with data: {command_data}")
        
        socketio.emit('capture_command', command_data, to=device_id)
        
        logger.info(f"[WEBAPP]  Capture command emitted to room: {device_id}")
        
    except Exception as e:
        logger.error(f"[CAPTURE]  Error handling capture request: {str(e)}")
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
        
        logger.info(f"[CAPTURE]  Received capture result from {device_id}, success: {success}")
        
        if not success:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"[CAPTURE]  Capture failed: {error_msg}")
            emit('capture_error', {'device_id': device_id, 'error': error_msg}, broadcast=True)
            return
        
        # Extract data
        image_url = data.get('image_url')
        timestamp = data.get('timestamp')
        
        logger.info(f"[CAPTURE] 📸 Image URL: {image_url}")
        
        # Get GPS from webapp gps_data_store (same as voice service)
        latitude = None
        longitude = None
        altitude = None
        gps_data = None
        
        logger.info(f"[CAPTURE] 🔍 device_id='{device_id}'")
        logger.info(f"[CAPTURE] 🔍 gps_data_store={gps_data_store}")
        logger.info(f"[CAPTURE] 🔍 store keys={list(gps_data_store.keys()) if gps_data_store else 'None'}")
        
        if gps_data_store and device_id in gps_data_store:
            gps_data = gps_data_store[device_id]
            latitude = gps_data.get('latitude')
            longitude = gps_data.get('longitude')
            altitude = gps_data.get('altitude', 0)
            logger.info(f"[CAPTURE] 📍 GPS from store: lat={latitude}, lon={longitude}, alt={altitude}")
        else:
            logger.warning(f"[CAPTURE] ⚠️ No GPS data in store for device: {device_id}")
        
        # Parse timestamp - handle ISO format with 'Z'
        capture_time = datetime.now()
        if timestamp:
            try:
                # Replace 'Z' with '+00:00' for proper ISO parsing
                timestamp_normalized = timestamp.replace('Z', '+00:00')
                capture_time = datetime.fromisoformat(timestamp_normalized)
            except Exception as ts_error:
                logger.warning(f"[CAPTURE] ⚠️ Could not parse timestamp '{timestamp}': {ts_error}")
        
        # Save to database
        db = SessionLocal()
        try:
            capture_record = CaptureRecord(
                device_id=device_id,
                original_image_url=image_url,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                analysis_status='pending',
                captured_at=capture_time
            )
            
            db.add(capture_record)
            db.commit()
            db.refresh(capture_record)
            
            logger.info(f"[CAPTURE] 💾 Saved to database with ID: {capture_record.id}")
            
            # Trigger AI analysis in background thread
            analysis_thread = threading.Thread(
                target=trigger_ai_analysis,
                args=(capture_record.id, image_url),
                daemon=True
            )
            analysis_thread.start()
            logger.info(f"[CAPTURE]  Started AI analysis thread for capture ID: {capture_record.id}")
            
        except Exception as db_error:
            logger.error(f"[CAPTURE]  Database error: {str(db_error)}")
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
        
        logger.info(f"[CAPTURE]  Capture processed and saved successfully")
        
    except Exception as e:
        logger.error(f"[CAPTURE]  Error handling capture result: {str(e)}")


# ============================================
# AI ANALYSIS FUNCTIONS
# ============================================

def trigger_ai_analysis(capture_id, image_url):
    """
    Send image to AI service for analysis (async with webhook callback)
    AI service returns 200 OK immediately, processes in background, then calls webhook
    """
    db = SessionLocal()
    try:
        logger.info(f"[CAPTURE AI]  Triggering AI analysis for capture ID: {capture_id}")
        logger.info(f"[CAPTURE AI]  Image URL: {image_url}")
        
        # Update status to 'processing'
        record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
        if record:
            record.analysis_status = 'processing'
            db.commit()
            logger.info(f"[CAPTURE AI]  Status: processing")
        
        # Send request to AI service (will return 200 OK immediately)
        # Webhook URL is hardcoded in AI service
        payload = {
            'image_url': image_url,
            'capture_id': capture_id
        }
        
        logger.info(f"[CAPTURE AI]  POST {AI_SERVICE_URL}/analyze")
        
        response = requests.post(
            f"{AI_SERVICE_URL}/analyze",
            json=payload,
            timeout=10  # Short timeout - just to receive acceptance
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"[CAPTURE AI]  Request accepted by AI service")
            logger.info(f"[CAPTURE AI] Response: {result}")
        else:
            logger.error(f"[CAPTURE AI]  AI service error: {response.status_code}")
            logger.error(f"[CAPTURE AI] Response: {response.text}")
            record.analysis_status = 'failed'
            db.commit()
                
    except requests.exceptions.Timeout:
        logger.error(f"[CAPTURE AI]  Timeout waiting for AI service acceptance")
        record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
        if record:
            record.analysis_status = 'failed'
            db.commit()
    except requests.exceptions.ConnectionError:
        logger.error(f"[CAPTURE AI]  Cannot connect to {AI_SERVICE_URL}")
        record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
        if record:
            record.analysis_status = 'failed'
            db.commit()
    except Exception as e:
        logger.error(f"[CAPTURE AI]  Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
        if record:
            record.analysis_status = 'failed'
            db.commit()
    finally:
        db.close()


# ============================================
# TEST ENDPOINT
# ============================================

@capture_blueprint.route('/api/capture/test', methods=['GET'])
def test_capture():
    """Test endpoint to verify capture controller is working"""
    logger.info("🧪 Test endpoint called!")
    return {
        'status': 'success',
        'message': 'Capture controller is working!',
        'timestamp': datetime.now().isoformat()
    }, 200


# ============================================
# WEBHOOK ENDPOINT
# ============================================

@capture_blueprint.route('/api/capture/webhook', methods=['POST'])
def capture_webhook():
    """
    Webhook endpoint called by AI service after analysis completes
    Receives: {capture_id, success, analyzed_image_url, person_count, earth_person_count, sea_person_count}
    """
    try:
        data = request.get_json()
        
        logger.info(f"[WEBHOOK]  Received callback from AI service")
        logger.info(f"[WEBHOOK] Data: {data}")
        
        capture_id = data.get('capture_id')
        success = data.get('success', False)
        
        if not capture_id:
            logger.error("[WEBHOOK] ❌ Missing capture_id")
            return {'status': 'error', 'message': 'capture_id required'}, 400
        
        db = SessionLocal()
        try:
            record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
            
            if not record:
                logger.error(f"[WEBHOOK] ❌ Capture ID {capture_id} not found")
                return {'status': 'error', 'message': 'Capture not found'}, 404
            
            if success:
                # Update with AI results
                record.analyzed_image_url = data.get('analyzed_image_url')
                record.person_count = data.get('person_count', 0)
                record.earth_person_count = data.get('earth_person_count', 0)
                record.sea_person_count = data.get('sea_person_count', 0)
                record.analysis_status = 'completed'
                record.analyzed_at = datetime.now()
                
                logger.info(f"[WEBHOOK] 💾 Updated capture ID {capture_id}")
                logger.info(f"[WEBHOOK] 👥 Total: {record.person_count}, Earth: {record.earth_person_count}, Sea: {record.sea_person_count}")
                
                # Notify frontend via Socket.IO
                socketio.emit('capture_analyzed', {
                    'capture_id': capture_id,
                    'analyzed_image_url': record.analyzed_image_url,
                    'person_count': record.person_count,
                    'earth_person_count': record.earth_person_count,
                    'sea_person_count': record.sea_person_count
                }, broadcast=True)
                
                logger.info(f"[WEBHOOK] 📡 Emitted capture_analyzed event to frontend")
                
            else:
                # Analysis failed
                error_msg = data.get('error', 'Unknown error')
                logger.error(f"[WEBHOOK] ❌ Analysis failed: {error_msg}")
                record.analysis_status = 'failed'
            
            db.commit()
            
            return {
                'status': 'success',
                'message': 'Webhook processed',
                'capture_id': capture_id
            }, 200
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"[WEBHOOK] ❌ Error processing webhook: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {'status': 'error', 'message': str(e)}, 500


# ============================================
# API ENDPOINTS
# ============================================

@capture_blueprint.route('/api/captures', methods=['GET'])
def get_captures():
    """
    Get list of all captures with optional filters
    Query params: device_id, status, limit
    """
    try:
        device_id = request.args.get('device_id')
        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)
        
        db = SessionLocal()
        try:
            query = db.query(CaptureRecord)
            
            if device_id:
                query = query.filter(CaptureRecord.device_id == device_id)
            if status:
                query = query.filter(CaptureRecord.analysis_status == status)
            
            records = query.order_by(CaptureRecord.created_at.desc()).limit(limit).all()
            
            return {
                'status': 'success',
                'count': len(records),
                'captures': [r.to_dict() for r in records]
            }, 200
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"[CAPTURE API] ❌ Error getting captures: {str(e)}")
        return {'status': 'error', 'message': str(e)}, 500


@capture_blueprint.route('/api/captures/<int:capture_id>', methods=['GET'])
def get_capture(capture_id):
    """
    Get details of a specific capture
    """
    try:
        db = SessionLocal()
        try:
            record = db.query(CaptureRecord).filter(CaptureRecord.id == capture_id).first()
            
            if not record:
                return {'status': 'error', 'message': 'Capture not found'}, 404
            
            return {
                'status': 'success',
                'capture': record.to_dict()
            }, 200
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"[CAPTURE API] ❌ Error getting capture {capture_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}, 500
