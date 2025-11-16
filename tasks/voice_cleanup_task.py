"""
Periodic cleanup task for stuck voice records
Run this via cron or a background scheduler (APScheduler, Celery Beat, etc.)
"""
import logging
from database import get_db
from services.voice_service import VoiceRecordService

logger = logging.getLogger(__name__)

def cleanup_stuck_voice_records(timeout_minutes: int = 10):
    """
    Cleanup records stuck in 'processing' state
    
    This function should be called periodically (recommended: every 5-10 minutes)
    
    Args:
        timeout_minutes: Records in processing older than this are marked failed
    
    Usage examples:
    
    1. Via cron (every 5 minutes):
       */5 * * * * cd /path/to/app && python3 -c "from tasks.voice_cleanup_task import cleanup_stuck_voice_records; cleanup_stuck_voice_records()"
    
    2. Via APScheduler (in app.py):
       from apscheduler.schedulers.background import BackgroundScheduler
       scheduler = BackgroundScheduler()
       scheduler.add_job(cleanup_stuck_voice_records, 'interval', minutes=5)
       scheduler.start()
    
    3. Via Flask-APScheduler:
       from flask_apscheduler import APScheduler
       scheduler = APScheduler()
       scheduler.add_job(id='cleanup_voice', func=cleanup_stuck_voice_records, 
                        trigger='interval', minutes=5)
       scheduler.start()
    """
    logger.info(f"[CLEANUP TASK] Starting stuck voice records cleanup (timeout: {timeout_minutes}m)")
    
    try:
        with get_db() as db:
            service = VoiceRecordService(db)
            count = service.cleanup_stuck_processing_records(timeout_minutes)
            
            if count > 0:
                logger.info(f"[CLEANUP TASK] Successfully cleaned up {count} stuck record(s)")
            else:
                logger.debug("[CLEANUP TASK] No stuck records found")
                
    except Exception as e:
        logger.error(f"[CLEANUP TASK] Cleanup failed: {str(e)}")
        raise

if __name__ == "__main__":
    # Allow running as standalone script for testing or manual cleanup
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get timeout from command line or use default
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    
    print(f"Running cleanup with {timeout} minute timeout...")
    cleanup_stuck_voice_records(timeout)
    print("Cleanup complete!")
