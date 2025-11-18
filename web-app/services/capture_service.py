"""
Service layer for Capture Record management
Handles business logic for image capture and AI analysis
"""
from model.capture_model import CaptureRecord
from datetime import datetime, timezone, timedelta
import logging
import requests
import threading

logger = logging.getLogger(__name__)

class CaptureRecordService:
    """Service for managing image capture records"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def create_record(self, device_id: str, latitude: float, longitude: float, 
                     image_url: str, altitude: float = 0):
        """
        Create a new capture record (immediate save, before AI analysis)
        """
        try:
            record = CaptureRecord(
                device_id=device_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                image_url=image_url,
                analysis_status='pending',
                captured_at=datetime.now(timezone.utc)
            )
            
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
            
            logger.info(f"[CAPTURE SERVICE] Created capture record ID: {record.id}")
            return record
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CAPTURE SERVICE] Error creating record: {str(e)}")
            raise
    
    def update_analysis(self, record_id: int, analyzed_image_url: str, 
                       total_count: int, earth_count: int, sea_count: int,
                       detections: list, error: str = None):
        """Update AI analysis results"""
        try:
            record = self.db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
            if record:
                logger.info(f"[CAPTURE SERVICE] 🔧 Updating record {record_id}:")
                logger.info(f"[CAPTURE SERVICE]   - Total persons: {total_count}")
                logger.info(f"[CAPTURE SERVICE]   - Earth persons: {earth_count}")
                logger.info(f"[CAPTURE SERVICE]   - Sea persons: {sea_count}")
                
                record.analyzed_image_url = analyzed_image_url
                record.total_person_count = total_count
                record.earth_person_count = earth_count
                record.sea_person_count = sea_count
                record.detections = detections
                record.analysis_status = 'completed' if not error else 'failed'
                record.analysis_error = error
                record.analyzed_at = datetime.now(timezone.utc)
                
                # Auto-set priority based on person count
                if total_count >= 5:
                    record.priority = 'critical'
                    record.is_urgent = True
                elif total_count >= 2:
                    record.priority = 'high'
                else:
                    record.priority = 'medium'
                
                self.db.commit()
                self.db.refresh(record)
                
                logger.info(f"[CAPTURE SERVICE] ✅ Saved to DB for record {record_id}")
                return record
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CAPTURE SERVICE] Error updating analysis: {str(e)}")
            raise
    
    def get_record(self, record_id: int):
        """Get a single capture record"""
        try:
            return self.db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
        except Exception as e:
            logger.error(f"[CAPTURE SERVICE] Error getting record: {str(e)}")
            raise
    
    def get_all_records(self, limit: int = 100, unresolved_only: bool = False):
        """Get all capture records"""
        try:
            query = self.db.query(CaptureRecord)
            
            if unresolved_only:
                query = query.filter(CaptureRecord.is_resolved == False)
            
            records = query.order_by(CaptureRecord.captured_at.desc()).limit(limit).all()
            return records
        except Exception as e:
            logger.error(f"[CAPTURE SERVICE] Error getting records: {str(e)}")
            raise
    
    def mark_resolved(self, record_id: int, notes: str = None):
        """Mark a capture record as resolved"""
        try:
            record = self.db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
            if record:
                record.is_resolved = True
                record.resolved_at = datetime.now(timezone.utc)
                if notes:
                    record.operator_notes = notes
                
                self.db.commit()
                logger.info(f"[CAPTURE SERVICE] Marked record {record_id} as resolved")
                return record
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CAPTURE SERVICE] Error marking resolved: {str(e)}")
            raise
    
    def delete_record(self, record_id: int):
        """Delete a capture record"""
        try:
            record = self.db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
            if record:
                self.db.delete(record)
                self.db.commit()
                logger.info(f"[CAPTURE SERVICE] Deleted record ID: {record_id}")
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CAPTURE SERVICE] Error deleting record: {str(e)}")
            raise
    
    def trigger_ai_analysis(self, record_id: int, ai_service_url: str, webapp_base_url: str):
        """
        Trigger AI analysis in background using daemon thread (gevent-compatible)
        Similar to voice service flow
        """
        def _background_ai_call():
            """Background thread worker for AI analysis"""
            import time
            from database import get_db
            
            try:
                # Small delay to let Flask/gevent handle other requests first
                time.sleep(0.1)
                
                # Create new DB session for this thread
                with get_db() as db_thread:
                    record = db_thread.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
                    if not record:
                        logger.error(f"[CAPTURE SERVICE BG] Record {record_id} not found for AI analysis")
                        return
                    
                    # Mark as processing
                    record.analysis_status = 'processing'
                    image_url = record.image_url
                    device_id = record.device_id
                    db_thread.commit()
                    
                    # Prepare webhook callback URL
                    webhook_url = f"{webapp_base_url}/api/captures/analysis/callback"
                    
                    # Prepare payload for AI service (Form data, not JSON)
                    payload = {
                        "image_url": image_url,
                        "device_id": device_id,
                        "record_id": record_id,
                        "webhook_url": webhook_url
                    }
                    
                    logger.info(f"[CAPTURE SERVICE BG] Sending record {record_id} to AI service: {ai_service_url}")
                    logger.info(f"[CAPTURE SERVICE BG] Payload: {payload}")
                    
                    # Call AI service with form data (timeout 10s for acknowledgment)
                    response = requests.post(
                        f"{ai_service_url}/analyze",
                        data=payload,  # Use 'data' for form-encoded, not 'json'
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"[CAPTURE SERVICE BG] ✅ AI analysis triggered for record {record_id}")
                    else:
                        logger.error(f"[CAPTURE SERVICE BG] ❌ AI service error: {response.status_code}")
                        with get_db() as db_fail:
                            record_fail = db_fail.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
                            if record_fail:
                                record_fail.analysis_status = 'failed'
                                record_fail.analysis_error = f"AI service error: {response.status_code}"
                                record_fail.analyzed_at = datetime.now(timezone.utc)
                                db_fail.commit()
                        
            except requests.exceptions.Timeout as timeout_error:
                logger.error(f"[CAPTURE SERVICE BG] AI service timeout for record {record_id}: {str(timeout_error)}")
                try:
                    with get_db() as db_timeout:
                        record_timeout = db_timeout.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
                        if record_timeout:
                            record_timeout.analysis_status = 'failed'
                            record_timeout.analysis_error = f"AI service timeout: {str(timeout_error)}"
                            record_timeout.analyzed_at = datetime.now(timezone.utc)
                            db_timeout.commit()
                            logger.info(f"[CAPTURE SERVICE BG] Record {record_id} marked as failed due to timeout")
                except Exception as db_error:
                    logger.error(f"[CAPTURE SERVICE BG] Failed to update record {record_id} after timeout: {str(db_error)}")
                    
            except Exception as e:
                logger.error(f"[CAPTURE SERVICE BG] Error in background AI analysis: {str(e)}")
                try:
                    with get_db() as db_error:
                        record_error = db_error.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
                        if record_error:
                            record_error.analysis_status = 'failed'
                            record_error.analysis_error = str(e)
                            record_error.analyzed_at = datetime.now(timezone.utc)
                            db_error.commit()
                except Exception as db_error:
                    logger.error(f"[CAPTURE SERVICE BG] Failed to update record status: {str(db_error)}")
        
        # Validate record exists before starting background thread
        record = None
        try:
            record = self.db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()
            if not record:
                logger.error(f"[CAPTURE SERVICE] Record {record_id} not found, cannot trigger AI analysis")
                return False
            
            # Use daemon thread (gevent-compatible)
            bg_thread = threading.Thread(
                target=_background_ai_call,
                name=f"capture_ai_{record_id}",
                daemon=True
            )
            bg_thread.start()
            
            logger.info(f"[CAPTURE SERVICE] Started background AI analysis thread for record {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"[CAPTURE SERVICE] Error starting background AI analysis: {str(e)}")
            
            if record is not None:
                try:
                    record.analysis_status = 'failed'
                    record.analysis_error = f"Failed to start analysis: {str(e)}"
                    record.analyzed_at = datetime.now(timezone.utc)
                    self.db.commit()
                except Exception as db_error:
                    logger.error(f"[CAPTURE SERVICE] Failed to update record {record_id} status: {str(db_error)}")
                    try:
                        self.db.rollback()
                    except Exception:
                        logger.exception(f"[CAPTURE SERVICE] Rollback failed for record {record_id}")
            
            return False
