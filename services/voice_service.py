"""
Service layer for Voice Record management
Handles business logic for voice distress records
"""
from model.voice_model import VoiceRecord
from datetime import datetime, timezone, timedelta
import logging
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
import atexit

logger = logging.getLogger(__name__)

# Module-level ThreadPoolExecutor for AI analysis tasks (bounded workers)
# Max 3 concurrent AI analysis calls to prevent resource exhaustion
_ai_analysis_executor = ThreadPoolExecutor(
    max_workers=3,
    thread_name_prefix="ai_analysis_worker"
)

def shutdown_ai_executor():
    """
    Gracefully shutdown the AI analysis executor
    Called during application shutdown to wait for in-flight tasks
    """
    logger.info("[VOICE SERVICE] Shutting down AI analysis executor...")
    # Note: timeout parameter only available in Python 3.12+
    # For Python 3.10, we just wait indefinitely for tasks to complete
    _ai_analysis_executor.shutdown(wait=True)
    logger.info("[VOICE SERVICE] AI analysis executor shutdown complete")

# Register shutdown handler
atexit.register(shutdown_ai_executor)

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
                recorded_at=datetime.now(timezone.utc)
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
                record.transcribed_at = datetime.now(timezone.utc)
                
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
                record.analyzed_at = datetime.now(timezone.utc)
                
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
                record.resolved_at = datetime.now(timezone.utc)
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
    
    def cleanup_stuck_processing_records(self, timeout_minutes: int = 10):
        """
        Find and mark records stuck in 'processing' state as failed
        
        This should be called periodically (e.g., via a cron job or scheduler)
        to recover from worker crashes, restarts, or network failures that leave
        records permanently stuck in 'processing' state.
        
        Args:
            timeout_minutes: Records in 'processing' state older than this are considered stuck
        
        Returns:
            Number of records cleaned up
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
            
            # Find records stuck in 'processing' state
            stuck_records = self.db.query(VoiceRecord).filter(
                VoiceRecord.analysis_status == 'processing',
                VoiceRecord.recorded_at < cutoff_time
            ).all()
            
            if not stuck_records:
                logger.debug(f"[VOICE SERVICE CLEANUP] No stuck records found (cutoff: {timeout_minutes}m)")
                return 0
            
            count = 0
            for record in stuck_records:
                try:
                    record.analysis_status = 'failed'
                    record.analysis_error = f"Analysis timed out (stuck in processing > {timeout_minutes} minutes)"
                    record.analyzed_at = datetime.now(timezone.utc)
                    count += 1
                    logger.warning(
                        f"[VOICE SERVICE CLEANUP] Marked stuck record {record.id} as failed "
                        f"(recorded at {record.recorded_at}, age: {datetime.now(timezone.utc) - record.recorded_at})"
                    )
                except Exception as record_error:
                    logger.error(f"[VOICE SERVICE CLEANUP] Failed to update stuck record {record.id}: {record_error}")
            
            if count > 0:
                self.db.commit()
                logger.info(f"[VOICE SERVICE CLEANUP] Cleaned up {count} stuck record(s)")
            
            return count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[VOICE SERVICE CLEANUP] Error during cleanup: {str(e)}")
            return 0
    
    def trigger_ai_analysis(self, record_id: int, ai_service_url: str):
        """
        Trigger AI analysis in background (truly async via daemon thread)
        This should be called AFTER the record is saved and returned to client
        Spawns a background thread that sends request to AI service with record_id and audio_url
        Returns immediately (True) after starting the background task
        """
        def _background_ai_call():
            """Background thread worker that performs the actual AI service call"""
            from database import get_db
            
            try:
                # Create a new DB session for this thread
                with get_db() as db_thread:
                    record = db_thread.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
                    if not record:
                        logger.error(f"[VOICE SERVICE BG] Record {record_id} not found for AI analysis")
                        return
                    
                    # Update status to processing
                    record.analysis_status = 'processing'
                    audio_url = record.audio_url  # Capture before commit
                    db_thread.commit()
                    
                    # Prepare payload for AI service
                    payload = {
                        "record_id": record_id,
                        "audio_url": audio_url
                    }
                    
                    logger.info(f"[VOICE SERVICE BG] Sending record {record_id} to AI service: {ai_service_url}")
                    logger.info(f"[VOICE SERVICE BG] Payload: {payload}")
                    
                    # Use a longer timeout since AI processing is slow (Whisper + LLM)
                    response = requests.post(ai_service_url, json=payload, timeout=180)
                    
                    if response.status_code == 200:
                        logger.info(f"[VOICE SERVICE BG] AI analysis triggered successfully for record {record_id}")
                    else:
                        logger.error(f"[VOICE SERVICE BG] AI service returned error: {response.status_code}")
                        # Update record with failure status
                        with get_db() as db_fail:
                            record_fail = db_fail.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
                            if record_fail:
                                record_fail.analysis_status = 'failed'
                                record_fail.analysis_error = f"AI service error: {response.status_code}"
                                record_fail.analyzed_at = datetime.now(timezone.utc)
                                db_fail.commit()
                        
            except requests.exceptions.Timeout as timeout_error:
                # Log timeout with details and record id
                logger.error(
                    f"[VOICE SERVICE BG] AI analysis timeout after 180s for record {record_id}: {str(timeout_error)}"
                )
                
                # Update record to a terminal failed state so it won't remain 'processing'
                try:
                    with get_db() as db_timeout:
                        record_timeout = db_timeout.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
                        if record_timeout:
                            record_timeout.analysis_status = 'failed'
                            record_timeout.analysis_error = f"AI service timeout after 180 seconds: {str(timeout_error)}"
                            record_timeout.analyzed_at = datetime.now(timezone.utc)
                            db_timeout.commit()
                            logger.info(f"[VOICE SERVICE BG] Record {record_id} marked as failed due to timeout")
                        else:
                            logger.error(f"[VOICE SERVICE BG] Timeout occurred but record {record_id} was not found in DB")
                except Exception as db_error:
                    logger.error(f"[VOICE SERVICE BG] Failed to update record {record_id} after timeout: {str(db_error)}")
                    
            except Exception as e:
                logger.error(f"[VOICE SERVICE BG] Error in background AI analysis: {str(e)}")
                try:
                    with get_db() as db_error:
                        record_error = db_error.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
                        if record_error:
                            record_error.analysis_status = 'failed'
                            record_error.analysis_error = str(e)
                            record_error.analyzed_at = datetime.now(timezone.utc)
                            db_error.commit()
                except Exception as db_error:
                    logger.error(f"[VOICE SERVICE BG] Failed to update record status: {str(db_error)}")
        
        # Validate record exists before starting background thread
        record = None  # Initialize to avoid NameError in exception handler
        try:
            record = self.db.query(VoiceRecord).filter(VoiceRecord.id == record_id).first()
            if not record:
                logger.error(f"[VOICE SERVICE] Record {record_id} not found, cannot trigger AI analysis")
                return False
            
            # Submit task to bounded ThreadPoolExecutor (non-daemon, survives until completion)
            future = _ai_analysis_executor.submit(_background_ai_call)
            
            # Optional: Add callback for task completion logging
            def _task_done_callback(future_obj):
                try:
                    future_obj.result()  # Raise exception if task failed
                    logger.debug(f"[VOICE SERVICE] AI analysis task completed for record {record_id}")
                except Exception as task_error:
                    logger.error(f"[VOICE SERVICE] AI analysis task failed for record {record_id}: {task_error}")
            
            future.add_done_callback(_task_done_callback)
            
            logger.info(f"[VOICE SERVICE] Submitted AI analysis task for record {record_id} to executor")
            return True
            
        except Exception as e:
            logger.error(f"[VOICE SERVICE] Error starting background AI analysis: {str(e)}")
            
            # Only update record if it was successfully loaded
            if record is not None:
                try:
                    record.analysis_status = 'failed'
                    record.analysis_error = f"Failed to start analysis: {str(e)}"
                    record.analyzed_at = datetime.now(timezone.utc)
                    self.db.commit()
                    logger.info(f"[VOICE SERVICE] Record {record_id} marked as failed due to startup error")
                except Exception as db_error:
                    logger.error(f"[VOICE SERVICE] Failed to update record {record_id} status: {str(db_error)}")
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.exception(f"[VOICE SERVICE] Rollback failed for record {record_id}")
            else:
                logger.warning(f"[VOICE SERVICE] Cannot update record status, record {record_id} was not loaded")
            
            return False
