"""
Detection utilities for periodic reporting
"""
import asyncio
import cv2
import base64
import logging
from datetime import datetime
import numpy as np

logger = logging.getLogger("drone-client")

# Global control variables
periodic_report_enabled = True
report_interval = 60  # Default 1 minute (60 seconds)


def set_report_interval(seconds):
    """Set the interval for periodic reports"""
    global report_interval
    if seconds < 60:  # Minimum 1 minute
        seconds = 60
    report_interval = seconds
    logger.info(f"Report interval set to {seconds} seconds ({seconds/60} minutes)")


def enable_periodic_report():
    """Enable periodic reporting"""
    global periodic_report_enabled
    periodic_report_enabled = True
    logger.info("Periodic reporting enabled")


def disable_periodic_report():
    """Disable periodic reporting"""
    global periodic_report_enabled
    periodic_report_enabled = False
    logger.info("Periodic reporting disabled")


def is_periodic_report_enabled():
    """Check if periodic reporting is enabled"""
    return periodic_report_enabled


def get_report_interval():
    """Get current report interval"""
    return report_interval


async def periodic_report_task(sio, device_id, device_name, video_track, interval=None):
    """
    Periodic task to capture snapshot and send detection report
    Args:
        sio: Socket.IO client instance
        device_id: Device ID
        device_name: Device name
        video_track: Video track instance to get frame and detection data
        interval: Report interval in seconds (default: use global report_interval)
    """
    global report_interval, periodic_report_enabled
    
    # Use global interval if not specified
    if interval is None:
        interval = report_interval
    
    logger.info(f"Started periodic detection report task (interval: {interval}s, enabled: {periodic_report_enabled})")
    
    while True:
        try:
            # Check if periodic reporting is enabled
            if not periodic_report_enabled:
                # If disabled, sleep for a short time and check again
                await asyncio.sleep(5)
                continue
            
            # Use current global interval
            current_interval = report_interval
            await asyncio.sleep(current_interval)
            
            if not video_track or not video_track.is_active():
                logger.warning("Video track not available, skipping report")
                continue
            
            # Get latest frame from buffer
            frame = video_track.frame_buffer.get_latest_frame()
            
            if frame is None:
                logger.warning("No frame available for report")
                continue
            
            # Get latest detection data
            detection_data = video_track.last_detection_data
            
            if not detection_data or detection_data.get('timestamp') is None:
                logger.warning("No detection data available for report")
                continue
            
            # Encode frame to JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare report data
            report_data = {
                'device_id': device_id,
                'device_name': device_name,
                'detection_data': {
                    'earth_person': detection_data.get('earth_person', 0),
                    'sea_person': detection_data.get('sea_person', 0),
                    'total': detection_data.get('total', 0),
                    'timestamp': datetime.now().isoformat()
                },
                'image': image_base64
            }
            
            # Send report to server
            await sio.emit('detection_snapshot', report_data)
            
            logger.info(f"Sent detection report: Earth={detection_data.get('earth_person', 0)}, "
                       f"Sea={detection_data.get('sea_person', 0)}, "
                       f"Total={detection_data.get('total', 0)}, "
                       f"Image size: {len(image_base64)} bytes")
            
        except asyncio.CancelledError:
            logger.info("Periodic report task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic report task: {e}", exc_info=True)
            # Continue running despite errors
            await asyncio.sleep(10)


async def on_demand_report(sio, device_id, device_name, video_track):
    """
    Capture and send detection report on demand
    """
    try:
        if not video_track or not video_track.is_active():
            logger.warning("Video track not available")
            return False
        
        # Get latest frame from buffer
        frame = video_track.frame_buffer.get_latest_frame()
        
        if frame is None:
            logger.warning("No frame available for on-demand report")
            return False
        
        # Get latest detection data
        detection_data = video_track.last_detection_data
        
        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Prepare report data
        report_data = {
            'device_id': device_id,
            'device_name': device_name,
            'detection_data': {
                'earth_person': detection_data.get('earth_person', 0),
                'sea_person': detection_data.get('sea_person', 0),
                'total': detection_data.get('total', 0),
                'timestamp': datetime.now().isoformat()
            },
            'image': image_base64
        }
        
        # Send report to server
        await sio.emit('detection_snapshot', report_data)
        
        logger.info(f"Sent on-demand detection report")
        return True
        
    except Exception as e:
        logger.error(f"Error in on-demand report: {e}", exc_info=True)
        return False
