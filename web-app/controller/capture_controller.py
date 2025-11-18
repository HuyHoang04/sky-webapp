"""
Capture Controller - Handles image capture and analysis endpoints
Receives images from Raspberry Pi, adds GPS from drone stream, triggers AI analysis in background
"""
from flask import Blueprint, request, jsonify
from database import get_db
from services.capture_service import CaptureRecordService
from socket_instance import socketio
import logging
import os

logger = logging.getLogger(__name__)

capture_blueprint = Blueprint('capture', __name__)

# Import GPS data store from gps_controller
from controller.gps_controller import gps_data_store

# AI Service URL (cloud-ai-server endpoint for image analysis)
AI_IMAGE_SERVICE_URL = os.getenv('AI_IMAGE_SERVICE_URL')
AI_ANALYSIS_ENABLED = bool(AI_IMAGE_SERVICE_URL)

# Webapp base URL for webhook callback
WEBAPP_BASE_URL = os.getenv('WEBAPP_BASE_URL', 'http://localhost:5000')

if not AI_ANALYSIS_ENABLED:
    logger.warning("[CAPTURE] ⚠️  AI_IMAGE_SERVICE_URL not configured, AI analysis will be disabled")
    logger.warning("[CAPTURE] Set AI_IMAGE_SERVICE_URL environment variable to enable AI detection and analysis")
else:
    logger.info(f"[CAPTURE] AI analysis enabled, using service at: {AI_IMAGE_SERVICE_URL}")
    logger.info(f"[CAPTURE] Webhook callback URL: {WEBAPP_BASE_URL}")

# ============================================
# CAPTURE API ENDPOINTS
# ============================================

@capture_blueprint.route('/api/captures', methods=['GET', 'POST'])
def handle_captures():
    """Get all capture records or create new capture"""
    if request.method == 'POST':
        try:
            data = request.json
            
            # Validate required fields
            required_fields = ['device_id', 'image_url']
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        'status': 'error',
                        'message': f'Missing required field: {field}'
                    }), 400
            
            # Get GPS from drone stream (socketio gps_data_store)
            latitude = None
            longitude = None
            altitude = 0
            
            if gps_data_store:
                # Get GPS data for the specific device_id or first available
                device_id = data['device_id']
                
                if device_id in gps_data_store:
                    gps_data = gps_data_store[device_id]
                else:
                    # Fallback to first available GPS
                    gps_device_id = list(gps_data_store.keys())[0]
                    gps_data = gps_data_store[gps_device_id]
                
                latitude = gps_data.get('latitude')
                longitude = gps_data.get('longitude')
                altitude = gps_data.get('altitude', 0)
                
                logger.info(f"[CAPTURE] Got GPS from drone: {latitude}, {longitude}, alt: {altitude}m")
            else:
                # Fallback GPS if no drone GPS available
                latitude = 21.0285  # Hanoi
                longitude = 105.8542
                altitude = 10
                logger.warning(f"[CAPTURE] No GPS stream available, using fallback coordinates")
            
            with get_db() as db:
                service = CaptureRecordService(db)
                
                # Create record with GPS from drone stream
                record = service.create_record(
                    device_id=data['device_id'],
                    latitude=float(latitude),
                    longitude=float(longitude),
                    altitude=float(altitude),
                    image_url=data['image_url']
                )
                
                record_id = record.id
                logger.info(f"[CAPTURE] Created record {record_id}")
            
            # Trigger AI analysis only if enabled
            if AI_ANALYSIS_ENABLED:
                logger.info(f"[CAPTURE] Triggering AI analysis for record {record_id}")
                
                try:
                    with get_db() as db_bg:
                        service_bg = CaptureRecordService(db_bg)
                        service_bg.trigger_ai_analysis(record_id, AI_IMAGE_SERVICE_URL, WEBAPP_BASE_URL)
                except Exception as e:
                    logger.error(f"[CAPTURE] Failed to trigger AI analysis: {str(e)}")
            else:
                logger.warning(f"[CAPTURE] AI analysis skipped for record {record_id} (AI_SERVICE_URL not configured)")
            
            # Return immediately to client with record data
            with get_db() as db:
                service = CaptureRecordService(db)
                record = service.get_record(record_id)
                
                response_message = 'Capture record created, AI analysis in progress' if AI_ANALYSIS_ENABLED else 'Capture record created (AI analysis disabled - configure AI_SERVICE_URL to enable)'
                
                return jsonify({
                    'status': 'success',
                    'message': response_message,
                    'record': record.to_dict(),
                    'ai_analysis_enabled': AI_ANALYSIS_ENABLED
                }), 201
                
        except Exception as e:
            logger.error(f"[CAPTURE] Error creating capture record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    else:  # GET
        try:
            # Optional filters
            unresolved_only = request.args.get('unresolved', 'false').lower() == 'true'
            limit = int(request.args.get('limit', 100))
            
            with get_db() as db:
                service = CaptureRecordService(db)
                records = service.get_all_records(limit=limit, unresolved_only=unresolved_only)
                
                return jsonify({
                    'status': 'success',
                    'count': len(records),
                    'records': [record.to_dict() for record in records]
                }), 200
                
        except Exception as e:
            logger.error(f"[CAPTURE] Error getting records: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@capture_blueprint.route('/api/captures/<int:record_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_capture_record(record_id):
    """Get, update, or delete a single capture record"""
    if request.method == 'GET':
        try:
            with get_db() as db:
                service = CaptureRecordService(db)
                record = service.get_record(record_id)
                
                if not record:
                    return jsonify({
                        'status': 'error',
                        'message': 'Record not found'
                    }), 404
                
                return jsonify({
                    'status': 'success',
                    'record': record.to_dict()
                }), 200
                
        except Exception as e:
            logger.error(f"[CAPTURE] Error getting record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    elif request.method == 'PUT':
        try:
            data = request.json or {}
            notes = data.get('notes')
            
            with get_db() as db:
                service = CaptureRecordService(db)
                record = service.mark_resolved(record_id, notes)
                
                if not record:
                    return jsonify({
                        'status': 'error',
                        'message': 'Record not found'
                    }), 404
                
                return jsonify({
                    'status': 'success',
                    'message': 'Record marked as resolved',
                    'record': record.to_dict()
                }), 200
                
        except Exception as e:
            logger.error(f"[CAPTURE] Error resolving record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    elif request.method == 'DELETE':
        try:
            with get_db() as db:
                service = CaptureRecordService(db)
                success = service.delete_record(record_id)
                
                if not success:
                    return jsonify({
                        'status': 'error',
                        'message': 'Record not found'
                    }), 404
                
                return jsonify({
                    'status': 'success',
                    'message': 'Record deleted successfully'
                }), 200
                
        except Exception as e:
            logger.error(f"[CAPTURE] Error deleting record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@capture_blueprint.route('/api/captures/analysis/callback', methods=['POST'])
def ai_analysis_callback():
    """
    Callback from AI service - receives analysis results
    
    Expected payload:
    {
        "record_id": int,
        "success": bool,
        "result": {
            "total_person": int,
            "earth_person_count": int,
            "sea_person_count": int,
            "detections": [...],
            "cloud_url": "https://..."
        }
    }
    """
    try:
        data = request.json
        
        record_id = data.get('record_id')
        success = data.get('success', False)
        result = data.get('result', {})
        
        if not record_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing record_id'
            }), 400
        
        with get_db() as db:
            service = CaptureRecordService(db)
            
            if success:
                # Extract analysis results
                analyzed_url = result.get('cloud_url')
                total_count = result.get('total_person', 0)
                earth_count = result.get('earth_person_count', 0)
                sea_count = result.get('sea_person_count', 0)
                detections = result.get('detections', [])
                
                logger.info(f"[CAPTURE CALLBACK] ✅ Received analysis for record {record_id}")
                logger.info(f"[CAPTURE CALLBACK]   - Total: {total_count}, Earth: {earth_count}, Sea: {sea_count}")
                
                # Update record with analysis results
                service.update_analysis(
                    record_id,
                    analyzed_url,
                    total_count,
                    earth_count,
                    sea_count,
                    detections
                )
                
            else:
                # Analysis failed
                error_msg = data.get('error', 'Unknown error')
                logger.error(f"[CAPTURE CALLBACK] ❌ Analysis failed for record {record_id}: {error_msg}")
                
                service.update_analysis(
                    record_id,
                    None, 0, 0, 0, [],
                    error=error_msg
                )
            
            return jsonify({
                'status': 'success',
                'message': 'Callback processed'
            }), 200
            
    except Exception as e:
        logger.error(f"[CAPTURE CALLBACK] Error processing callback: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================
# SOCKET.IO HANDLERS FOR CAPTURE
# ============================================

@socketio.on('capture_request')
def handle_capture_request(data):
    """
    Handle capture request from dashboard
    Forward to drone via socket to capture image
    """
    try:
        device_id = data.get('device_id', 'drone-camera')
        
        logger.info(f"[CAPTURE SOCKET] 📸 Received capture request for device: {device_id}")
        
        # Emit to specific drone device (if in room) or broadcast to all
        socketio.emit('capture_command', {
            'device_id': device_id,
            'timestamp': data.get('timestamp'),
            'quality': 95  # High quality
        }, to=device_id)  # Use 'to' instead of 'room' for better compatibility
        
        logger.info(f"[CAPTURE SOCKET] ✅ Sent capture command to device: {device_id}")
        
    except Exception as e:
        logger.error(f"[CAPTURE SOCKET] Error handling capture request: {str(e)}")


@socketio.on('capture_result')
def handle_capture_result(data):
    """
    Handle capture result from drone
    Drone sends back image_url after uploading to Cloudinary
    """
    try:
        device_id = data.get('device_id')
        image_url = data.get('image_url')
        success = data.get('success', True)
        
        # Check if drone reported an error
        if not success:
            error_msg = data.get('error', 'Unknown error')
            logger.error(f"[CAPTURE SOCKET] Drone reported error: {error_msg}")
            socketio.emit('capture_error', {
                'device_id': device_id,
                'error': error_msg
            })
            return
        
        if not device_id or not image_url:
            logger.error(f"[CAPTURE SOCKET] Missing required fields in capture result")
            return
        
        logger.info(f"[CAPTURE SOCKET] ✅ Received capture result from {device_id}: {image_url}")
        
        # Get GPS from drone (prioritize GPS sent with capture result)
        gps_from_drone = data.get('gps_data')
        latitude = None
        longitude = None
        altitude = 0
        
        if gps_from_drone:
            # Use GPS data sent by drone at capture time
            latitude = gps_from_drone.get('latitude')
            longitude = gps_from_drone.get('longitude')
            altitude = gps_from_drone.get('altitude', 0)
            logger.info(f"[CAPTURE SOCKET] 📍 GPS from drone: {latitude}, {longitude}, alt: {altitude}m")
        elif gps_data_store and device_id in gps_data_store:
            # Fallback to GPS stream data
            gps_data = gps_data_store[device_id]
            latitude = gps_data.get('latitude')
            longitude = gps_data.get('longitude')
            altitude = gps_data.get('altitude', 0)
            logger.info(f"[CAPTURE SOCKET] 📍 GPS from stream: {latitude}, {longitude}, alt: {altitude}m")
        elif gps_data_store:
            # Fallback to first available GPS
            gps_device_id = list(gps_data_store.keys())[0]
            gps_data = gps_data_store[gps_device_id]
            latitude = gps_data.get('latitude')
            longitude = gps_data.get('longitude')
            altitude = gps_data.get('altitude', 0)
            logger.warning(f"[CAPTURE SOCKET] ⚠️ Using GPS from other device: {gps_device_id}")
        else:
            # Fallback coordinates (Hanoi)
            latitude = 21.0285
            longitude = 105.8542
            altitude = 10
            logger.warning(f"[CAPTURE SOCKET] ⚠️ No GPS available, using fallback coordinates")
        
        # Create record in database
        with get_db() as db:
            service = CaptureRecordService(db)
            record = service.create_record(
                device_id=device_id,
                latitude=float(latitude),
                longitude=float(longitude),
                altitude=float(altitude),
                image_url=image_url
            )
            
            record_id = record.id
            logger.info(f"[CAPTURE SOCKET] Created record {record_id}")
        
        # Trigger AI analysis
        if AI_ANALYSIS_ENABLED:
            logger.info(f"[CAPTURE SOCKET] Triggering AI analysis for record {record_id}")
            try:
                with get_db() as db_bg:
                    service_bg = CaptureRecordService(db_bg)
                    service_bg.trigger_ai_analysis(record_id, AI_IMAGE_SERVICE_URL, WEBAPP_BASE_URL)
            except Exception as e:
                logger.error(f"[CAPTURE SOCKET] Failed to trigger AI: {str(e)}")
        
        # Notify dashboard about successful capture
        socketio.emit('capture_success', {
            'device_id': device_id,
            'record_id': record_id,
            'image_url': image_url,
            'message': 'Capture successful, AI analysis in progress'
        })
        
        logger.info(f"[CAPTURE SOCKET] ✅ Capture workflow completed for record {record_id}")
        
    except Exception as e:
        logger.error(f"[CAPTURE SOCKET] Error handling capture result: {str(e)}")
        socketio.emit('capture_error', {
            'device_id': data.get('device_id'),
            'error': str(e)
        })
