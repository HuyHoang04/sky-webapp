"""
Voice Controller - Handles voice distress record endpoints
Receives audio from Raspberry Pi, adds GPS from drone stream, triggers AI analysis in background
"""
from flask import Blueprint, request, jsonify, render_template
from database import get_db
from services.voice_service import VoiceRecordService
import logging
import threading
import os
import time

logger = logging.getLogger(__name__)

voice_blueprint = Blueprint('voice', __name__)

# Import GPS data store from gps_controller
from controller.gps_controller import gps_data_store

# AI Service URL (analytics-voice-server endpoint)
AI_SERVICE_URL = os.getenv('AI_SERVICE_URL')
AI_ANALYSIS_ENABLED = bool(AI_SERVICE_URL)

if not AI_ANALYSIS_ENABLED:
    logger.warning("[VOICE] ⚠️  AI_SERVICE_URL not configured, AI analysis will be disabled")
    logger.warning("[VOICE] Set AI_SERVICE_URL environment variable to enable AI transcription and analysis")
else:
    logger.info(f"[VOICE] AI analysis enabled, using service at: {AI_SERVICE_URL}")
# ============================================
# WEB ROUTES
# ============================================

@voice_blueprint.route('/voice')
def voice_page():
    """Render voice records management page"""
    return render_template('voice.html')

# ============================================
# VOICE RECORD API ENDPOINTS
# ============================================

@voice_blueprint.route('/api/voice/records', methods=['GET', 'POST'])
def handle_voice_records():
    """Get all voice records or create new record"""
    if request.method == 'POST':
        try:
            data = request.json
            
            # Validate required fields (GPS not required from mic device)
            required_fields = ['device_id', 'audio_url']
            for field in required_fields:
                if field not in data:
                    return jsonify({
                        'status': 'error',
                        'message': f'Missing required field: {field}'
                    }), 400
            
            # Get GPS from drone stream (socketio gps_data_store)
            # Try to get GPS from the most recent drone in the system
            latitude = None
            longitude = None
            altitude = 0
            
            if gps_data_store:
                # Get the first available GPS data (assuming single drone)
                # You can customize this to select specific device_id if needed
                gps_device_id = list(gps_data_store.keys())[0]
                gps_data = gps_data_store[gps_device_id]
                
                latitude = gps_data.get('latitude')
                longitude = gps_data.get('longitude')
                altitude = gps_data.get('altitude', 0)
                
                logger.info(f"[VOICE] Got GPS from drone {gps_device_id}: {latitude}, {longitude}, alt: {altitude}m")
            else:
                # Fallback GPS if no drone GPS available
                latitude = 21.0285  # Hanoi
                longitude = 105.8542
                altitude = 10
                logger.warning(f"[VOICE] No GPS stream available, using fallback coordinates")
            
            # Safely parse and validate duration (default: 15 seconds, bounds: 1-300 seconds)
            duration = 15  # default
            try:
                duration_input = data.get('duration', 15)
                duration = int(duration_input)
                # Enforce reasonable bounds (1 second to 5 minutes)
                if duration < 1:
                    duration = 1
                    logger.warning(f"[VOICE] Duration too low, clamped to 1 second")
                elif duration > 300:
                    duration = 300
                    logger.warning(f"[VOICE] Duration too high, clamped to 300 seconds")
            except (ValueError, TypeError) as e:
                logger.warning(f"[VOICE] Invalid duration value '{data.get('duration')}': {e}, using default 15s")
                duration = 15
            
            with get_db() as db:
                service = VoiceRecordService(db)
                
                # Create record with GPS from drone stream
                record = service.create_record(
                    device_id=data['device_id'],
                    latitude=float(latitude),
                    longitude=float(longitude),
                    altitude=float(altitude),
                    audio_url=data['audio_url'],
                    duration=duration
                )
                
                record_id = record.id
                logger.info(f"[VOICE] Created record {record_id} (duration: {duration}s)")
            
            # Trigger AI analysis only if enabled
            if AI_ANALYSIS_ENABLED:
                logger.info(f"[VOICE] Triggering AI analysis for record {record_id}")
                
                # Service already handles background threading, no need for double-threading
                try:
                    with get_db() as db_bg:
                        service_bg = VoiceRecordService(db_bg)
                        service_bg.trigger_ai_analysis(record_id, AI_SERVICE_URL)
                except Exception as e:
                    logger.error(f"[VOICE] Failed to trigger AI analysis: {str(e)}")
            else:
                logger.warning(f"[VOICE] AI analysis skipped for record {record_id} (AI_SERVICE_URL not configured)")
            
            # Return immediately to client with record data
            with get_db() as db:
                service = VoiceRecordService(db)
                record = service.get_record(record_id)
                
                response_message = 'Voice record created, AI analysis in progress' if AI_ANALYSIS_ENABLED else 'Voice record created (AI analysis disabled - configure AI_SERVICE_URL to enable)'
                
                return jsonify({
                    'status': 'success',
                    'message': response_message,
                    'record': record.to_dict(),
                    'ai_analysis_enabled': AI_ANALYSIS_ENABLED
                }), 201
                
        except Exception as e:
            logger.error(f"[VOICE] Error creating voice record: {str(e)}")
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
                service = VoiceRecordService(db)
                records = service.get_all_records(limit=limit, unresolved_only=unresolved_only)
                
                # 🔍 DEBUG LOG: Check first record with analysis
                for record in records:
                    if record.analysis_items:
                        logger.info(f"[VOICE API] 📤 Sending record {record.id} to frontend:")
                        logger.info(f"[VOICE API]   - Intent: {record.analysis_intent}")
                        logger.info(f"[VOICE API]   - Items: {record.analysis_items}")
                        break
                
                return jsonify({
                    'status': 'success',
                    'count': len(records),
                    'records': [record.to_dict() for record in records]
                }), 200
                
        except Exception as e:
            logger.error(f"[VOICE] Error getting records: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@voice_blueprint.route('/api/voice/records/<int:record_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_voice_record(record_id):
    """Get, update, or delete a single voice record"""
    if request.method == 'GET':
        try:
            with get_db() as db:
                service = VoiceRecordService(db)
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
            logger.error(f"[VOICE] Error getting record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    elif request.method == 'PUT':
        try:
            data = request.json or {}
            notes = data.get('notes')
            
            with get_db() as db:
                service = VoiceRecordService(db)
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
            logger.error(f"[VOICE] Error resolving record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    elif request.method == 'DELETE':
        try:
            with get_db() as db:
                service = VoiceRecordService(db)
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
            logger.error(f"[VOICE] Error deleting record: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@voice_blueprint.route('/api/voice/analysis/callback', methods=['POST'])
def ai_analysis_callback():
    """
    Callback from AI service - receives 2 separate callbacks:
    
    CALLBACK 1 (FAST - Transcription only):
    {
        "record_id": int,
        "success": bool,
        "stage": "transcription",
        "result": {
            "text_goc": "transcribed text",
            "analysis": null
        }
    }
    
    CALLBACK 2 (SLOW - Analysis):
    {
        "record_id": int,
        "success": bool,
        "stage": "analysis",
        "result": {
            "text_goc": "transcribed text",
            "analysis": {
                "intent": "Cứu Gấp | Bị thương | Đói/Khát | Không rõ",
                "items": ["item1", "item2"]
            }
        }
    }
    """
    try:
        data = request.json
        
        record_id = data.get('record_id')
        stage = data.get('stage', 'unknown')  # 'transcription' hoặc 'analysis'
        
        if not record_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing record_id'
            }), 400
        
        with get_db() as db:
            service = VoiceRecordService(db)
            
            if data.get('success') and 'result' in data:
                result = data['result']
                
                if stage == 'transcription':
                    # CALLBACK 1: Chỉ update transcription (NHANH)
                    if 'text_goc' in result:
                        service.update_transcription(record_id, result['text_goc'])
                        logger.info(f"[VOICE CALLBACK 1] ✅ Transcription updated for record {record_id}")
                        
                        return jsonify({
                            'status': 'success',
                            'message': 'Transcription updated (stage 1)'
                        }), 200
                
                elif stage == 'analysis':
                    # CALLBACK 2: Update analysis (CHẬM)
                    if 'analysis' in result and result['analysis']:
                        analysis = result['analysis']
                        intent = analysis.get('intent', 'Không rõ')
                        items = analysis.get('items', [])
                        error = analysis.get('error')
                        
                        # 🔍 DEBUG LOG: Print full callback data
                        logger.info(f"[VOICE CALLBACK 2] 📦 Full result data: {result}")
                        logger.info(f"[VOICE CALLBACK 2] 🧠 Analysis object: {analysis}")
                        logger.info(f"[VOICE CALLBACK 2] 🎯 Intent: {intent}")
                        logger.info(f"[VOICE CALLBACK 2] 📋 Items: {items} (type: {type(items)})")
                        
                        service.update_analysis(record_id, intent, items, error)
                        logger.info(f"[VOICE CALLBACK 2] ✅ Analysis updated for record {record_id}: {intent} with {len(items)} items")
                        
                        return jsonify({
                            'status': 'success',
                            'message': 'Analysis updated (stage 2)'
                        }), 200
                
                else:
                    # Fallback: cả 2 cùng lúc (backward compatibility)
                    if 'text_goc' in result:
                        service.update_transcription(record_id, result['text_goc'])
                        logger.info(f"[VOICE] Updated transcription for record {record_id}")
                    
                    if 'analysis' in result and result['analysis']:
                        analysis = result['analysis']
                        intent = analysis.get('intent', 'Không rõ')
                        items = analysis.get('items', [])
                        error = analysis.get('error')
                        
                        service.update_analysis(record_id, intent, items, error)
                        logger.info(f"[VOICE] Updated analysis for record {record_id}: {intent}")
                    
                    return jsonify({
                        'status': 'success',
                        'message': 'Results updated'
                    }), 200
            else:
                # Analysis failed
                error_msg = data.get('error', 'Unknown error')
                service.update_analysis(record_id, None, [], error_msg)
                logger.error(f"[VOICE] AI processing failed for record {record_id}: {error_msg}")
        
        return jsonify({
            'status': 'success',
            'message': 'Callback processed'
        }), 200
        
    except Exception as e:
        logger.error(f"[VOICE] Error in AI callback: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@voice_blueprint.route('/api/voice/trigger-recording', methods=['POST'])
def trigger_recording():
    """
    Trigger emergency recording via Socket.IO
    Sends event to record system (Raspberry Pi)
    """
    try:
        from socket_instance import socketio
        
        # Emit socket event to record device
        logger.info("[VOICE] Triggering recording via Socket.IO")
        socketio.emit('trigger_recording', {
            'timestamp': time.time(),
            'source': 'web_dashboard'
        })
        
        return jsonify({
            'status': 'success',
            'message': 'Recording trigger sent to device'
        }), 200
        
    except Exception as e:
        logger.error(f"[VOICE] Error triggering recording: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500
