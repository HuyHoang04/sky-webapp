"""
Service layer for Voice Record management
Handles business logic for voice distress records
"""
from model.voice_model import VoiceRecord
from datetime import datetime
import logging
import requests
import threading

logger = logging.getLogger(__name__)

class VoiceRecordService:
    """Service for managing voice distress records"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def create_record(self, device_id: str, latitude: float, longitude: float, 
                     audio_url: str, altitude: float = 0, duration: int = 15):
        """
        Create a new voice record (immediate save, before AI analysis)
        """
        try:
            record = VoiceRecord(
                device_id=device_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                audio_url=audio_url,
                duration_seconds=duration,
                transcription_status='pending',
                analysis_status='pending',
                recorded_at=datetime.utcnow()
            )
            
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            
            logger.info(f"[VOICE SERVICE] Created voice record ID: {record.id}")
            return record
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE] Error creating record: {str(e)}")
            raise
    
    def update_transcription(self, record_id: int, text: str):
        """Update transcription text (quick update)"""
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if record:
                record.transcribed_text = text
                record.transcription_status = 'completed' if text else 'failed'
                record.transcribed_at = datetime.utcnow()
                
                self.db.commit()
                logger.info(f"[VOICE SERVICE] Updated transcription for record ID: {record_id}")
                return record
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE] Error updating transcription: {str(e)}")
            raise
    
    def update_analysis(self, record_id: int, intent: str, items: list, error: str = None):
        """Update AI analysis results (slow update, happens later)"""
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if record:
                record.analysis_intent = intent
                record.analysis_items = items
                record.analysis_status = 'completed' if not error else 'failed'
                record.analysis_error = error
                record.analyzed_at = datetime.utcnow()
                
                # Auto-set priority based on intent
                if intent in ['Cứu Gấp', 'Bị thương']:
                    record.priority = 'critical'
                    record.is_urgent = True
                elif intent == 'Đói/Khát':
                    record.priority = 'high'
                else:
                    record.priority = 'medium'
                
                self.db.commit()
                logger.info(f"[VOICE SERVICE] Updated analysis for record ID: {record_id}")
                return record
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE] Error updating analysis: {str(e)}")
            raise
    
    def get_record(self, record_id: int):
        """Get a single voice record"""
        try:
            return self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
        except Exception as e:
            logger.error(f"[VOICE SERVICE] Error getting record: {str(e)}")
            raise
    
    def get_all_records(self, limit: int = 100, unresolved_only: bool = False):
        """Get all voice records"""
        try:
            query = self.db.query(VoiceRecord)
            
            if unresolved_only:
                query = query.filter(VoiceRecord.is_resolved == False)
            
            records = query.order_by(VoiceRecord.recorded_at.desc()).limit(limit).all()
            return records
        except Exception as e:
            logger.error(f"[VOICE SERVICE] Error getting records: {str(e)}")
            raise
    
    def mark_resolved(self, record_id: int, notes: str = None):
        """Mark a voice record as resolved"""
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if record:
                record.is_resolved = True
                record.resolved_at = datetime.utcnow()
                if notes:
                    record.operator_notes = notes
                
                self.db.commit()
                logger.info(f"[VOICE SERVICE] Marked record {record_id} as resolved")
                return record
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE] Error marking resolved: {str(e)}")
            raise
    
    def delete_record(self, record_id: int):
        """Delete a voice record"""
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if record:
                self.db.delete(record)
                self.db.commit()
                logger.info(f"[VOICE SERVICE] Deleted record ID: {record_id}")
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE] Error deleting record: {str(e)}")
            raise
    
    def trigger_ai_analysis(self, record_id: int, ai_service_url: str):
        """
        Trigger AI analysis in background (async call to AI service)
        This should be called AFTER the record is saved and returned to client
        Sends request to AI service with record_id and audio_url
        """
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if not record:
                logger.error(f"[VOICE SERVICE] Record {record_id} not found for AI analysis")
                return False
            
            # Update status to processing
            record.analysis_status = 'processing'
            self.db.commit()
            
            # Prepare payload for AI service
            payload = {
                "record_id": record_id,
                "audio_url": record.audio_url
            }
            
            logger.info(f"[VOICE SERVICE] Sending record {record_id} to AI service: {ai_service_url}")
            logger.info(f"[VOICE SERVICE] Payload: {payload}")
            
            # Use a longer timeout since AI processing is slow (Whisper + LLM)
            response = requests.post(ai_service_url, json=payload, timeout=180)
            
            if response.status_code == 200:
                logger.info(f"[VOICE SERVICE] AI analysis triggered for record {record_id}")
                return True
            else:
                logger.error(f"[VOICE SERVICE] AI service returned error: {response.status_code}")
                record.analysis_status = 'failed'
                record.analysis_error = f"AI service error: {response.status_code}"
                self.db.commit()
                return False
                
        except requests.exceptions.Timeout:
            logger.warning(f"[VOICE SERVICE] AI analysis timeout for record {record_id} - continuing in background")
            return True  # Still return True as analysis is likely happening
        except Exception as e:
            logger.error(f"[VOICE SERVICE] Error triggering AI analysis: {str(e)}")
            record.analysis_status = 'failed'
            record.analysis_error = str(e)
            self.db.commit()
            return False
