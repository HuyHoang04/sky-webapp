#!/usr/bin/env python3
"""
Drone App Client for Sky WebApp
Streams video via WebRTC with object detection and sends GPS data via WebSocket
"""

import argparse
import asyncio
import json
import logging
import os
import time
import uuid
import threading
from datetime import datetime
import nest_asyncio

import cv2
import numpy as np
import socketio
import inspect
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay
from av import VideoFrame
from camera_utils import setup_camera, load_onnx_model
from gps_utils import read_gps, gps_task
from video_stream import ObjectDetectionStreamTrack
import io
import cloudinary
import cloudinary.uploader

CLOUD_NAME="de8dmh7iq"
CLOUD_API_KEY="878738396278587"
CLOUD_API_SECRET="TvLHcRpcWaA4Vl1zmjOl23lc9rY"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("drone-client")

# Default configuration - Optimized for real-time streaming
DEFAULT_SERVER_URL = "https://popular-catfish-slightly.ngrok-free.app"
DEFAULT_DEVICE_ID = "drone-camera"  # Fixed device ID for easier debugging
DEFAULT_DEVICE_NAME = "Drone Camera"

# ========== VIDEO STREAMING CONFIGURATION (Có thể chỉnh tại đây) ==========
DEFAULT_FPS = 50  # Frames per second (15-30 fps recommended)
DEFAULT_WIDTH = 1280  # Video width in pixels
DEFAULT_HEIGHT = 720  # Video height in pixels
DEFAULT_BITRATE = 3000000  # Video bitrate in bits/s (4Mbps default, 3-6Mbps recommended for 720p)
                           # Lower = less bandwidth but lower quality
                           # Higher = better quality but more bandwidth
DEFAULT_DETECTION_FRAME_INTERVAL = 3  # AI detection runs every N frames (3 = ~10x/sec at 30fps)
                                        # Higher = less CPU usage but slower detection updates
DEFAULT_DETECTION_PUBLISH_INTERVAL = 0.5  # seconds between detection publishes to server (faster updates)

# DUAL THRESHOLD STRATEGY (Config 7A: tested and optimized)
DEFAULT_CONFIDENCE_THRESHOLD = 0.05  # Fallback/general threshold
DEFAULT_EARTH_PERSON_THRESHOLD = 0.06  # earth_person confidence (aerial: 4 detections)
DEFAULT_SEA_PERSON_THRESHOLD = 0.03    # sea_person confidence (flood: 6E+5S detections)
                                        # sea_person has higher confidence scores (max 0.57 vs 0.36)
DEFAULT_NMS_IOU_THRESHOLD = 0.1        # NMS IoU threshold (Config 7A optimal value)
                                        # 0.1 provides good balance for both scenarios
# ===========================================================================

DEFAULT_GPS_INTERVAL = 1.0  # seconds
ICE_GATHERING_TIMEOUT = 5  # seconds
RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_ATTEMPTS = 10

# Socket.IO client
sio = socketio.AsyncClient(reconnection=True, reconnection_attempts=MAX_RECONNECT_ATTEMPTS, 
                          reconnection_delay=RECONNECT_DELAY)

# Global variables
peer_connection = None
device_id = DEFAULT_DEVICE_ID
device_name = DEFAULT_DEVICE_NAME
relay = MediaRelay()
webcam = None
gps_task_runner = None
running = True
ort_session = None
reconnect_task = None
video_track = None
capture_server_task = None
pending_remote_ice = []
user_stopped = False
detection_task = None
latest_gps = None
webrtc_restart_count = 0
last_restart_time = 0

# 💓 ICE Keepalive
keepalive_task = None
stats_monitor_task = None


async def create_peer_connection():
    """Create a new RTCPeerConnection with proper event handlers"""
    global peer_connection, video_track
    
    # Close any existing connection
    if peer_connection:
        await peer_connection.close()
    
    # Create a new RTCPeerConnection with multiple STUN servers for redundancy
    config = RTCConfiguration(
        iceServers=[
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun2.l.google.com:19302"]),
            RTCIceServer(urls=["turn:relay1.expressturn.com:3480"], username="000000002076929768", credential="glxmCqGZVm2WqKrB/EXZsf2SZGc="),
        ]
    )
    peer_connection = RTCPeerConnection(config)
    
    # Log connection state changes
    @peer_connection.on("connectionstatechange")
    async def on_connectionstatechange():
        state = peer_connection.connectionState
        logger.info(f"PeerConnection state: {state}")
        
        if state == "failed" or state == "closed":
            # Connection failed, try to restart
            logger.warning("WebRTC connection failed or closed, will attempt to restart")
            await asyncio.sleep(1)
            await restart_webrtc()
    
    # Log ICE connection state changes
    @peer_connection.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        state = peer_connection.iceConnectionState
        logger.info(f"ICE connection state: {state}")
        
        # 💓 Start keepalive when ICE is connected
        if state == "connected" or state == "completed":
            logger.info("🎯 ICE CONNECTED - Starting keepalive mechanism")
            await start_keepalive()
            
            # Ensure AI detection starts AFTER ICE connection is established
            if video_track:
                logger.info("🎯 ICE CONNECTED - AI detection should now be processing frames")
                # Log detection worker status
                if hasattr(video_track, 'detection_thread') and video_track.detection_thread:
                    is_alive = video_track.detection_thread.is_alive()
                    logger.info(f"🤖 AI detection worker thread status: {'RUNNING ✅' if is_alive else 'STOPPED ❌'}")
                    if not is_alive:
                        logger.error("⚠️ AI detection worker thread is NOT running! Restarting...")
                        # Restart detection thread
                        video_track.detection_thread = threading.Thread(target=video_track._detection_worker, daemon=True)
                        video_track.detection_thread.start()
                        logger.info("✅ AI detection worker thread restarted")
                else:
                    logger.warning("⚠️ Video track has no detection thread!")
        elif state == "failed" or state == "disconnected":
            logger.warning(f"ICE connection {state} - stopping keepalive")
            await stop_keepalive()
    
    # Log ICE gathering state changes
    @peer_connection.on("icegatheringstatechange")
    async def on_icegatheringstatechange():
        logger.info(f"ICE gathering state: {peer_connection.iceGatheringState}")
    
    # Handle ICE candidates
    @peer_connection.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            logger.debug(f"Generated local ICE candidate: {candidate.candidate}")
    
    # Add video track if webcam is available
    if webcam:
        # Create a new video track or reuse existing one
        if not video_track:
            video_track = ObjectDetectionStreamTrack(webcam, DEFAULT_FPS, DEFAULT_WIDTH, DEFAULT_HEIGHT, ort_session, detection_interval=DEFAULT_DETECTION_FRAME_INTERVAL)
        # Capture the sender so we can tune RTP encoding parameters (bitrate/framerate)
        try:
            sender = peer_connection.addTrack(video_track)
            logger.info("Added video track to peer connection")

            # Configure RTP encoding using configurable parameters
            try:
                params = sender.getParameters()
                # Ensure encodings list exists
                if not getattr(params, 'encodings', None):
                    params.encodings = [{'maxBitrate': DEFAULT_BITRATE, 'maxFramerate': DEFAULT_FPS}]
                else:
                    # Update the first encoding entry with desired constraints
                    try:
                        params.encodings[0].update({'maxBitrate': DEFAULT_BITRATE, 'maxFramerate': DEFAULT_FPS})
                    except Exception:
                        params.encodings = [{'maxBitrate': DEFAULT_BITRATE, 'maxFramerate': DEFAULT_FPS}]

                # setParameters may be synchronous or return an awaitable depending on aiortc version
                try:
                    res = sender.setParameters(params)
                    if inspect.isawaitable(res):
                        await res
                except Exception as e:
                    logger.warning(f"Could not set RTP sender parameters: {e}")
                else:
                    logger.info(f"RTP encoding set: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT}@{DEFAULT_FPS}fps, bitrate={DEFAULT_BITRATE/1000000:.1f}Mbps")
            except Exception as e:
                logger.debug(f"Skipping sender parameter tuning: {e}")
        except Exception as e:
            # Ensure we still log adding track failure but continue
            logger.error(f"Failed to add video track to peer connection: {e}")
    else:
        logger.warning("No webcam available, cannot add video track")
    
    return peer_connection


async def create_offer():
    """Create a WebRTC offer with proper ICE gathering"""
    global peer_connection
    
    # Ensure we have a usable peer connection. If the existing one is closed/failed, recreate it.
    if not peer_connection or getattr(peer_connection, 'connectionState', None) in ('closed', 'failed'):
        logger.debug('PeerConnection missing or closed/failed, creating a new one')
        await create_peer_connection()
    
    # Create offer
    offer = await peer_connection.createOffer()
    await peer_connection.setLocalDescription(offer)
    logger.info("Created offer and set as local description")
    
    # Wait for ICE gathering to complete with timeout
    start_time = time.time()
    while peer_connection.iceGatheringState != "complete":
        if time.time() - start_time > ICE_GATHERING_TIMEOUT:
            logger.warning(f"ICE gathering timed out after {ICE_GATHERING_TIMEOUT}s, proceeding with available candidates")
            break
        await asyncio.sleep(0.1)
    
    # Return the SDP offer with all gathered ICE candidates
    return {
        "sdp": peer_connection.localDescription.sdp,
        "type": peer_connection.localDescription.type,
    }


async def start_keepalive():
    """💓 Start ICE keepalive mechanism"""
    global keepalive_task, stats_monitor_task
    
    # Stop existing tasks
    await stop_keepalive()
    
    logger.info("💓 Starting ICE keepalive mechanism")
    
    # Keepalive ping task
    async def keepalive_ping():
        while running and peer_connection:
            try:
                if peer_connection.connectionState != "connected":
                    logger.debug("💓 Keepalive stopped - connection not active")
                    break
                
                ice_state = peer_connection.iceConnectionState
                logger.info(f"💓 Keepalive ping - ICE: {ice_state}, RTC: {peer_connection.connectionState}")
                
                # Check if ICE connection is unhealthy
                if ice_state in ["disconnected", "failed"]:
                    logger.warning(f"💓 Keepalive detected ICE issue: {ice_state}")
                    
            except Exception as e:
                logger.error(f"💓 Keepalive ping error: {e}")
                break
            
            await asyncio.sleep(5)  # Ping every 5 seconds
    
    # Stats monitoring task
    async def stats_monitor():
        last_bytes_sent = 0
        last_packets_sent = 0
        last_check_time = time.time()
        
        while running and peer_connection:
            try:
                if peer_connection.connectionState != "connected":
                    logger.debug("📊 Stats monitor stopped - connection not active")
                    break
                
                # Get stats
                stats = await peer_connection.getStats()
                bytes_sent = 0
                packets_sent = 0
                packets_lost = 0
                
                for report in stats.values():
                    if hasattr(report, 'type') and report.type == 'outbound-rtp':
                        bytes_sent += getattr(report, 'bytesSent', 0)
                        packets_sent += getattr(report, 'packetsSent', 0)
                        packets_lost += getattr(report, 'packetsLost', 0)
                
                # Calculate deltas
                bytes_delta = bytes_sent - last_bytes_sent
                packets_delta = packets_sent - last_packets_sent
                time_delta = time.time() - last_check_time
                
                if bytes_delta > 0 or packets_delta > 0:
                    bitrate = (bytes_delta * 8) / time_delta / 1000  # kbps
                    logger.info(f"📊 Stats - Sent: {bytes_delta} bytes, {packets_delta} packets, {bitrate:.1f} kbps, Lost: {packets_lost}")
                else:
                    logger.warning(f"⚠️ Stats - No data sent in last {time_delta:.1f}s")
                
                # Update last values
                last_bytes_sent = bytes_sent
                last_packets_sent = packets_sent
                last_check_time = time.time()
                
            except Exception as e:
                logger.error(f"📊 Stats monitor error: {e}")
                break
            
            await asyncio.sleep(10)  # Check every 10 seconds
    
    # Start tasks
    keepalive_task = asyncio.create_task(keepalive_ping())
    stats_monitor_task = asyncio.create_task(stats_monitor())
    logger.info("💓 Keepalive and stats monitoring started")


async def stop_keepalive():
    """💓 Stop ICE keepalive mechanism"""
    global keepalive_task, stats_monitor_task
    
    if keepalive_task and not keepalive_task.done():
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        keepalive_task = None
        logger.info("💓 Keepalive stopped")
    
    if stats_monitor_task and not stats_monitor_task.done():
        stats_monitor_task.cancel()
        try:
            await stats_monitor_task
        except asyncio.CancelledError:
            pass
        stats_monitor_task = None
        logger.info("📊 Stats monitoring stopped")


async def restart_webrtc():
    """Restart the WebRTC connection with retry limit"""
    global webrtc_restart_count, last_restart_time, pending_remote_ice
    
    # Stop keepalive during restart
    await stop_keepalive()
    
    # Rate limiting - don't restart too frequently
    now = time.time()
    if now - last_restart_time < 10:  # Min 10 seconds between restarts
        webrtc_restart_count += 1
        if webrtc_restart_count > 3:
            logger.warning(f"⚠️ Too many WebRTC restarts ({webrtc_restart_count}), backing off...")
            await asyncio.sleep(30)  # Wait 30s before trying again
            webrtc_restart_count = 0
    else:
        # Reset counter if enough time has passed
        webrtc_restart_count = 0
    
    last_restart_time = now
    logger.info(f"🔄 Restarting WebRTC connection (attempt #{webrtc_restart_count + 1})")
    
    try:
        # Clear any buffered ICE candidates before restarting
        pending_remote_ice = []

        # Create a new offer
        offer = await create_offer()
        
        # Send the offer to the server
        logger.info(f"Sending new webrtc_offer for device: {device_id}")
        await sio.emit('webrtc_offer', {
            'device_id': device_id,
            'sdp': offer['sdp'],
            'type': offer['type']
        })
    except Exception as e:
        logger.error(f"Failed to restart WebRTC: {e}")


def _nms_boxes(boxes, scores, iou_threshold=0.5):
    """Simple NMS for boxes in [x1,y1,x2,y2] format."""
    if len(boxes) == 0:
        return []
    boxes = np.array(boxes)
    scores = np.array(scores)
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= iou_threshold)[0]
        order = order[inds + 1]
    return keep


def parse_onnx_detections(outputs, input_size=(640, 640), orig_size=None, conf_threshold=0.05, iou_threshold=0.35, 
                           earth_threshold=None, sea_threshold=None):
    """Parser for YOLOv8 ONNX output format: [1, 6, 8400]
    Format: [x, y, w, h, conf_class0, conf_class1]
    Returns list of detections: {'bbox':[x1,y1,x2,y2],'score':float,'class':int}
    
    Args:
        earth_threshold: Optional separate threshold for earth_person (class 0)
        sea_threshold: Optional separate threshold for sea_person (class 1)
    """
    # DEBUG: Log output shapes
    logger.debug(f"🔍 ONNX outputs count: {len(outputs)}")
    for i, out in enumerate(outputs):
        if isinstance(out, np.ndarray):
            logger.debug(f"   Output[{i}] shape: {out.shape}, dtype: {out.dtype}")
    
    dets = []
    
    # YOLOv8 format: [1, 6, 8400] -> transpose to [8400, 6]
    if len(outputs) > 0:
        out = outputs[0]
        if isinstance(out, np.ndarray) and out.ndim == 3 and out.shape[0] == 1:
            # Shape: [1, 6, 8400] -> transpose to [8400, 6]
            out = out[0].T  # Now shape is [8400, 6]
            logger.debug(f"   Transposed to shape: {out.shape}")
            
            # Parse each detection
            for detection in out:
                x, y, w, h = detection[0], detection[1], detection[2], detection[3]
                conf_class0 = detection[4]  # earth_person
                conf_class1 = detection[5]  # sea_person
                
                # Use separate thresholds if provided, otherwise use general threshold
                thresh_c0 = earth_threshold if earth_threshold is not None else conf_threshold
                thresh_c1 = sea_threshold if sea_threshold is not None else conf_threshold
                
                # Check both classes with their respective thresholds
                detected = False
                cls = None
                conf = 0.0
                
                if conf_class0 >= thresh_c0 and conf_class0 > conf_class1:
                    cls = 0
                    conf = conf_class0
                    detected = True
                elif conf_class1 >= thresh_c1 and conf_class1 >= conf_class0:
                    cls = 1
                    conf = conf_class1
                    detected = True
                
                if not detected:
                    continue
                
                # Convert center format (x,y,w,h) to corner format (x1,y1,x2,y2)
                x1 = x - w / 2.0
                y1 = y - h / 2.0
                x2 = x + w / 2.0
                y2 = y + h / 2.0
                
                dets.append({
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'score': float(conf),
                    'class': int(cls)
                })
            
            logger.debug(f"   Found {len(dets)} detections before NMS")
    
    # Old fallback parser (keep for compatibility)
    if not dets:
        for out in outputs:
            if not isinstance(out, np.ndarray):
                continue
            if out.size == 0:
                continue
            arr = out
            if arr.ndim == 3 and arr.shape[0] == 1:
                arr = arr[0]
            if arr.ndim != 2:
                try:
                    arr = arr.reshape(-1, arr.shape[-1])
                except Exception:
                    continue

            C = arr.shape[1]
            logger.debug(f"   Fallback: Processing array shape: {arr.shape}, columns: {C}")
        if C >= 6:
            sample = arr[0]
            is_norm = float(sample[0]) <= 1.01 and float(sample[1]) <= 1.01
            for row in arr:
                try:
                    row = row.astype(float)
                except Exception:
                    continue
                if C >= 6:
                    cx, cy, w, h = row[0], row[1], row[2], row[3]
                    conf = float(row[4])
                    cls = int(row[5]) if C >= 6 else 0
                    if conf < conf_threshold:
                        continue
                    if is_norm:
                        iw, ih = input_size
                        cx *= iw
                        cy *= ih
                        w *= iw
                        h *= ih
                    x1 = cx - w / 2.0
                    y1 = cy - h / 2.0
                    x2 = cx + w / 2.0
                    y2 = cy + h / 2.0
                    dets.append({'bbox': [float(x1), float(y1), float(x2), float(y2)], 'score': float(conf), 'class': int(cls)})
        elif C == 5:
            for row in arr:
                try:
                    x1, y1, x2, y2, conf = row.astype(float)
                except Exception:
                    continue
                if conf < conf_threshold:
                    continue
                dets.append({'bbox': [float(x1), float(y1), float(x2), float(y2)], 'score': float(conf), 'class': 0})
        else:
            if C > 6:
                for row in arr:
                    try:
                        row = row.astype(float)
                    except Exception:
                        continue
                    cx, cy, w, h, conf = row[0], row[1], row[2], row[3], row[4]
                    class_probs = row[5:]
                    cls = int(np.argmax(class_probs))
                    cls_prob = float(np.max(class_probs))
                    score = conf * cls_prob
                    if score < conf_threshold:
                        continue
                    iw, ih = input_size
                    if cx <= 1.01 and cy <= 1.01:
                        cx *= iw
                        cy *= ih
                        w *= iw
                        h *= ih
                    x1 = cx - w / 2.0
                    y1 = cy - h / 2.0
                    x2 = cx + w / 2.0
                    y2 = cy + h / 2.0
                    dets.append({'bbox': [float(x1), float(y1), float(x2), float(y2)], 'score': float(score), 'class': int(cls)})

    if orig_size is not None and dets:
        iw, ih = input_size
        ow, oh = orig_size
        sx = ow / float(iw)
        sy = oh / float(ih)
        for d in dets:
            x1, y1, x2, y2 = d['bbox']
            d['bbox'] = [x1 * sx, y1 * sy, x2 * sx, y2 * sy]

    final = []
    if dets:
        boxes = [d['bbox'] for d in dets]
        scores = [d['score'] for d in dets]
        keep_idxs = _nms_boxes(boxes, scores, iou_threshold=iou_threshold)
        for i in keep_idxs:
            final.append(dets[i])

    return final


async def detection_publisher_loop(sio_client, webcam, ort_session, video_track_ref=None, interval=DEFAULT_DETECTION_PUBLISH_INTERVAL):
    """Background task: periodically emit detection results from video_track cache to server via Socket.IO
    
    This ensures the detection counts match exactly what's shown on the video stream.
    """
    logger.info("Starting detection publisher loop (using video_track cached detections)")
    try:
        while True:
            try:
                if not sio_client.connected:
                    await asyncio.sleep(1.0)
                    continue

                detections = []
                
                # CRITICAL: Get detections from video_track cache to match what's shown on screen
                if video_track_ref is not None and hasattr(video_track_ref, 'cached_detections'):
                    # Thread-safe copy of cached detections
                    if hasattr(video_track_ref, 'detection_lock'):
                        with video_track_ref.detection_lock:
                            detections = video_track_ref.cached_detections.copy() if video_track_ref.cached_detections else []
                    else:
                        detections = video_track_ref.cached_detections.copy() if video_track_ref.cached_detections else []
                    
                    if detections:
                        logger.debug(f"Using {len(detections)} detections from video_track cache")
                else:
                    logger.debug("No video_track reference, skipping detection publish")
                
                # Count by class (0: earth_person, 1: sea_person)
                earth_person_count = sum(1 for d in detections if d.get('class') == 0)
                sea_person_count = sum(1 for d in detections if d.get('class') == 1)
                total_person_count = earth_person_count + sea_person_count

                payload = {
                    'device_id': device_id,
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'earth_person_count': earth_person_count,
                    'sea_person_count': sea_person_count,
                    'person_count': total_person_count,
                    'detections': [{'bbox': d['bbox'], 'class': d['class'], 'score': d['score']} for d in detections[:20]],
                    'gps': latest_gps,
                }
                try:
                    await sio_client.emit('detection_result', payload)
                    if total_person_count > 0:
                        logger.info(f"📊 Published detection: earth={earth_person_count}, sea={sea_person_count}, total={total_person_count}")
                    else:
                        logger.debug(f"Published detection: no objects detected")
                except Exception as e:
                    logger.debug(f"Failed to emit detection_result: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in detection publisher loop: {e}")

            await asyncio.sleep(interval)
    finally:
        logger.info('Detection publisher loop stopped')


@sio.event
async def connect():
    """Handle Socket.IO connection"""
    logger.info(f"[DRONE] ✅ Connected to server as device_id: {device_id}")
    
    # Register device
    logger.info(f"[DRONE] 📡 Registering as video device: {device_id}")
    await sio.emit(
        "register_video_device",
        {
            "device_id": device_id,
            "device_name": device_name,
            "capabilities": {
                "width": DEFAULT_WIDTH,
                "height": DEFAULT_HEIGHT,
                "fps": DEFAULT_FPS,
            },
        },
    )
    logger.info(f"[DRONE] ✅ Video device registration sent")
    
    # Create and send WebRTC offer
    try:
        offer = await create_offer()
        logger.info(f"Sending webrtc_offer for device: {device_id}")
        await sio.emit('webrtc_offer', {
            'device_id': device_id,
            'sdp': offer['sdp'],
            'type': offer['type']
        })
    except Exception as e:
        logger.error(f"Failed to create WebRTC offer: {e}")
    
    
    # Start real GPS task with latest_gps update
    global gps_task_runner, running, latest_gps, detection_task
    if gps_task_runner and not gps_task_runner.done():
        gps_task_runner.cancel()

    async def _gps_reader():
        """Read GPS from gps_utils.read_gps and update latest_gps while forwarding to server."""
        global latest_gps
        try:
            async for gps in read_gps(serial_port="/dev/ttyAMA3", baudrate=9600):
                latest_gps = gps
                gps['device_id'] = device_id
                gps['device_name'] = device_name
                try:
                    await sio.emit('gps_data', gps)
                except Exception:
                    pass
                await asyncio.sleep(DEFAULT_GPS_INTERVAL)
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"GPS reader error: {e}")

    gps_task_runner = asyncio.create_task(_gps_reader())
    logger.info("Started GPS reader task")
    
    # Start detection publisher
    if detection_task and not detection_task.done():
        detection_task.cancel()
    # Pass video_track reference to publisher so it can read cached detections
    detection_task = asyncio.create_task(detection_publisher_loop(sio, webcam, ort_session, video_track_ref=video_track))
    logger.info("Started detection publisher task (synced with video_track)")
    


@sio.event
async def disconnect():
    """Handle Socket.IO disconnection"""
    logger.info("Disconnected from server")
    
    # Don't set running to False here to allow reconnection
    # Just cancel the GPS task, it will be restarted on reconnect
    if gps_task_runner and not gps_task_runner.done():
        gps_task_runner.cancel()


@sio.event
async def webrtc_offer(data):
    """Handle incoming WebRTC offer from frontend"""
    # In our optimized design, the drone is always the offerer
    # We'll log this but ignore it to prevent negotiation glare
    logger.info("Received webrtc_offer from frontend, but drone is configured as offerer")


@sio.event
async def start_webrtc(data):
    """Handle start request from frontend - create and send an offer"""
    global user_stopped
    try:
        requested_device = data.get('device_id')
        logger.info(f"Received start_webrtc request from server/frontend: {data}")
        
        # Only respond if this request is for this drone
        if requested_device and requested_device != device_id:
            logger.debug(f"Ignoring start_webrtc for device '{requested_device}' (I am '{device_id}')")
            return
        
        user_stopped = False
        await restart_webrtc()
    except Exception as e:
        logger.error(f"Error handling start_webrtc: {e}")


@sio.event
async def stop_webrtc(data):
    """Handle stop request from frontend - close peer and stop track"""
    global user_stopped, peer_connection, video_track
    try:
        requested_device = data.get('device_id')
        logger.info(f"Received stop_webrtc request for device: {requested_device}")
        
        # Only respond if this request is for this drone
        if requested_device and requested_device != device_id:
            logger.debug(f"Ignoring stop_webrtc for device '{requested_device}' (I am '{device_id}')")
            return
        
        user_stopped = True
        
        # Stop keepalive
        await stop_keepalive()
        
        if video_track:
            try:
                video_track.stop()
            except Exception:
                pass
            video_track = None
        if peer_connection:
            try:
                await peer_connection.close()
            except Exception:
                pass
            peer_connection = None
        logger.info('Stopped WebRTC as requested')
    except Exception as e:
        logger.error(f"Error handling stop_webrtc: {e}")


@sio.event
async def webrtc_answer(data):
    """Handle WebRTC answer from server"""
    try:
        # Ensure we have a usable peer connection; recreate if needed
        if not peer_connection or getattr(peer_connection, 'connectionState', None) in ('closed', 'failed'):
            logger.debug('PeerConnection missing or closed/failed when receiving answer; creating a new one')
            await create_peer_connection()

        if peer_connection:
            answer = RTCSessionDescription(sdp=data['sdp'], type=data['type'])
            await peer_connection.setRemoteDescription(answer)
            logger.info("WebRTC answer received and set successfully")
            # After setting remote description, add any buffered ICE candidates
            global pending_remote_ice
            if pending_remote_ice:
                logger.info(f"🔄 [DRONE] Adding {len(pending_remote_ice)} buffered remote ICE candidates")
                for cand in pending_remote_ice:
                        try:
                            # Parse and add buffered candidate
                            if isinstance(cand, dict):
                                candidate_str = cand.get('candidate')
                                sdp_mid = cand.get('sdpMid')
                                sdp_mline_index = cand.get('sdpMLineIndex')
                                
                                parts = candidate_str.split()
                                foundation = parts[0].split(':')[1]
                                component = int(parts[1])
                                protocol = parts[2]
                                priority = int(parts[3])
                                ip = parts[4]
                                port = int(parts[5])
                                typ = parts[7]
                                
                                related_address = None
                                related_port = None
                                i = 8
                                while i < len(parts):
                                    if parts[i] == 'raddr' and i + 1 < len(parts):
                                        related_address = parts[i + 1]
                                        i += 2
                                    elif parts[i] == 'rport' and i + 1 < len(parts):
                                        related_port = int(parts[i + 1])
                                        i += 2
                                    else:
                                        i += 1
                                
                                rtc_cand = RTCIceCandidate(
                                    component=component,
                                    foundation=foundation,
                                    ip=ip,
                                    port=port,
                                    priority=priority,
                                    protocol=protocol,
                                    type=typ,
                                    relatedAddress=related_address,
                                    relatedPort=related_port,
                                    sdpMid=sdp_mid,
                                    sdpMLineIndex=sdp_mline_index
                                )
                                await peer_connection.addIceCandidate(rtc_cand)
                            else:
                                await peer_connection.addIceCandidate(cand)
                            logger.info(f"✅ [DRONE] Added buffered ICE candidate")
                        except Exception as e:
                            logger.error(f"❌ [DRONE] Failed to add buffered ICE candidate: {e}")
                pending_remote_ice = []
        else:
            logger.error("Received webrtc_answer but no peer connection exists")
    except Exception as e:
        # If answer cannot be applied because signaling state is stable (race), log and skip restart
        msg = str(e)
        if 'Cannot handle answer in signaling state' in msg or 'in signaling state "stable"' in msg:
            logger.warning(f"Ignoring answer due to signaling state race: {e}")
            return
        logger.error(f"Error setting remote description: {e}")
        # Try to recover by restarting WebRTC
        await asyncio.sleep(1)
        await restart_webrtc()


@sio.event
async def webrtc_ice_candidate(data):
    """Handle ICE candidate from server"""
    try:
        candidate_payload = data.get('candidate') if isinstance(data, dict) else None
        
        if not candidate_payload:
            logger.debug('webrtc_ice_candidate called with no candidate payload')
            return

        # Debug log the incoming candidate payload structure
        logger.debug(f"Incoming ICE candidate keys: {candidate_payload.keys() if isinstance(candidate_payload, dict) else 'not a dict'}")

        # If peer connection or its remote description is not ready yet, buffer the candidate
        if not peer_connection or getattr(peer_connection, 'remoteDescription', None) is None:
            logger.debug('PeerConnection or remoteDescription not ready, buffering ICE candidate')
            pending_remote_ice.append(candidate_payload)
            return

        try:
            # Parse candidate string manually (aiortc doesn't have from_sdp method)
            if isinstance(candidate_payload, dict):
                candidate_str = candidate_payload.get('candidate')
                sdp_mid = candidate_payload.get('sdpMid')
                sdp_mline_index = candidate_payload.get('sdpMLineIndex')
                
                # Parse candidate string: "candidate:foundation component protocol priority ip port typ type ..."
                # Example: "candidate:2202223057 1 udp 2113937151 34a70fd6-ca00-4d5b-b443-cbfaf4f6c257.local 60815 typ host generation 0 ufrag lc5w network-cost 999"
                parts = candidate_str.split()
                if len(parts) < 8:
                    raise ValueError(f"Invalid candidate string: {candidate_str}")
                
                # Extract fields
                foundation = parts[0].split(':')[1]  # "candidate:2202223057" -> "2202223057"
                component = int(parts[1])
                protocol = parts[2]
                priority = int(parts[3])
                ip = parts[4]
                port = int(parts[5])
                # parts[6] is "typ"
                typ = parts[7]
                
                # Optional fields
                related_address = None
                related_port = None
                tcp_type = None
                
                # Parse remaining optional fields
                i = 8
                while i < len(parts):
                    if parts[i] == 'raddr' and i + 1 < len(parts):
                        related_address = parts[i + 1]
                        i += 2
                    elif parts[i] == 'rport' and i + 1 < len(parts):
                        related_port = int(parts[i + 1])
                        i += 2
                    elif parts[i] == 'tcptype' and i + 1 < len(parts):
                        tcp_type = parts[i + 1]
                        i += 2
                    else:
                        i += 1
                
                # Create RTCIceCandidate object
                rtc_cand = RTCIceCandidate(
                    component=component,
                    foundation=foundation,
                    ip=ip,
                    port=port,
                    priority=priority,
                    protocol=protocol,
                    type=typ,
                    relatedAddress=related_address,
                    relatedPort=related_port,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index,
                    tcpType=tcp_type
                )
                
                await peer_connection.addIceCandidate(rtc_cand)
                logger.debug(f'✅ [DRONE] Added ICE candidate: {typ} {ip}:{port}')
            else:
                # If it's already an RTCIceCandidate object, add it directly
                await peer_connection.addIceCandidate(candidate_payload)
                logger.debug('✅ [DRONE] Added ICE candidate (direct)')
        except Exception as e:
            logger.error(f'Failed to add ICE candidate: {e}. Buffering candidate.')
            logger.error(f'❌ [DRONE] Failed to add ICE candidate: {e}')
            logger.debug(f'🔄 [DRONE] Buffering candidate')
            pending_remote_ice.append(candidate_payload)
    except Exception as e:
        logger.error(f"Error handling ICE candidate: {e}")


@sio.event
async def capture_command(data):
    """Handle capture command from server (via Socket.IO)"""
    try:
        device_id_from_server = data.get('device_id')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        logger.info(f"📸 [DRONE] Received capture_command from server")
        logger.info(f"📸 [DRONE] Data received: {data}")
        logger.info(f"📸 [DRONE] My device_id: {device_id}")
        logger.info(f"📸 [DRONE] Server device_id: {device_id_from_server}")
        
        # Verify device ID matches
        if device_id_from_server != device_id:
            logger.warning(f"📸 [DRONE] Device ID mismatch: {device_id_from_server} != {device_id}")
            return
        
        # Capture image from camera
        if not webcam:
            logger.error("Camera not available for capture")
            await sio.emit('capture_result', {
                'device_id': device_id,
                'success': False,
                'error': 'Camera not available'
            })
            return
        
        # Get high-quality frame from camera
        frame = webcam.get_frame()
        if frame is None:
            logger.error("Failed to capture frame from camera")
            await sio.emit('capture_result', {
                'device_id': device_id,
                'success': False,
                'error': 'Failed to capture frame'
            })
            return
        
        logger.info("📸 Frame captured successfully")
        
        # Encode to JPEG with high quality
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        img_bytes = buffer.tobytes()
        
        # Read GPS data if available
        gps_data = None
        if latest_gps:
            gps_data = {
                'latitude': latest_gps.get('latitude'),
                'longitude': latest_gps.get('longitude'),
                'altitude': latest_gps.get('altitude'),
                'speed': latest_gps.get('speed')
            }
            logger.info(f"📍 GPS data: {gps_data}")
        
        # Upload to Cloudinary
        try:
            # Cloudinary config
            cloudinary.config(
                cloud_name=CLOUD_NAME,
                api_key=CLOUD_API_KEY,
                api_secret=CLOUD_API_SECRET,
                secure=True
            )
            
            logger.info("☁️ Uploading to Cloudinary...")
            result = cloudinary.uploader.upload(
                io.BytesIO(img_bytes),
                folder="drone_captures",
                resource_type="image",
                public_id=f"capture_{device_id}_{int(time.time())}"
            )
            
            image_url = result.get('secure_url')
            logger.info(f"✅ Image uploaded: {image_url}")
            
            # Send result back to server via Socket.IO
            await sio.emit('capture_result', {
                'device_id': device_id,
                'success': True,
                'image_url': image_url,
                'gps_data': gps_data,
                'timestamp': timestamp
            })
            
            logger.info("📤 Capture result sent to server")
            
        except Exception as upload_error:
            logger.error(f"Failed to upload to Cloudinary: {upload_error}")
            await sio.emit('capture_result', {
                'device_id': device_id,
                'success': False,
                'error': f'Upload failed: {str(upload_error)}'
            })
            
    except Exception as e:
        logger.error(f"Error handling capture command: {e}")
        await sio.emit('capture_result', {
            'device_id': device_id,
            'success': False,
            'error': str(e)
        })


async def health_check():
    """Periodic health check for WebRTC connection"""
    while running:
        try:
            # If user explicitly stopped the stream, skip health restarts
            if user_stopped:
                await asyncio.sleep(30)
                continue

            if peer_connection and peer_connection.connectionState not in ["connected", "connecting"]:
                logger.warning(f"WebRTC connection in unhealthy state: {peer_connection.connectionState}")
                await restart_webrtc()
            
            # Check if video track is working
            if video_track and not video_track.is_active():
                logger.warning("Video track is not active, attempting to restart")
                await restart_webrtc()
                
        except Exception as e:
            logger.error(f"Error in health check: {e}")
        
        await asyncio.sleep(30)  # Check every 30 seconds


async def cleanup():
    """Clean up resources"""
    global running, peer_connection, webcam, video_track
    
    running = False
    
    # Stop keepalive
    await stop_keepalive()
    
    # Cancel tasks
    if gps_task and not gps_task.done():
        gps_task.cancel()
    
    # Close peer connection
    if peer_connection:
        await peer_connection.close()
        peer_connection = None
    
    # Release video track
    if video_track:
        video_track.stop()
        video_track = None
    
    # Release webcam
    if webcam:
        webcam.release()
        webcam = None

    # Stop capture API server if running
    global capture_server_task, detection_task
    if capture_server_task and not capture_server_task.done():
        capture_server_task.cancel()
        try:
            await capture_server_task
        except Exception:
            pass
    
    # Stop detection task
    if detection_task and not detection_task.done():
        detection_task.cancel()
        try:
            await detection_task
        except Exception:
            pass
    
    # Disconnect from server
    if sio.connected:
        await sio.disconnect()


async def main():
    """Main function"""
    global webcam, ort_session, running, device_id, device_name, gps_task_runner, running
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Drone App Client")
    parser = argparse.ArgumentParser(description="Drone App Client")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL, help="Server URL")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Device ID")
    parser.add_argument("--device-name", default=DEFAULT_DEVICE_NAME, help="Device name")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Video width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Video height")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Video FPS")
    parser.add_argument("--model", default="nano_model_fp32.onnx", help="Path to ONNX model (use FP32, INT8 has zero confidence issue)")
    parser.add_argument("--no-detection", action="store_true", help="Disable object detection")

    args = parser.parse_args()
    
    logger.info(f"Server URL: {DEFAULT_SERVER_URL}")
    
    # Set global variables
    device_id = args.device_id
    device_name = args.device_name
    
    # Load ONNX model if detection is enabled
    if not args.no_detection:
        logger.info(f"Loading ONNX model from {args.model}")
        ort_session = await load_onnx_model(args.model)
        if not ort_session:
            logger.warning("Failed to load ONNX model, object detection will be disabled")
    else:
        logger.info("Object detection disabled by command line argument")
    
    # Setup camera with retry mechanism
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries and not webcam:
        logger.info(f"Setting up camera (attempt {retry_count + 1}/{max_retries})")
        webcam = await setup_camera(args.width, args.height, args.fps)
        
        if not webcam:
            retry_count += 1
            if retry_count < max_retries:
                logger.warning(f"Failed to setup camera, retrying in 2 seconds...")
                await asyncio.sleep(2)
            else:
                logger.error("Failed to setup camera after multiple attempts")
                return
    
    logger.info("Camera setup successful")

    
    # Start health check task
    health_check_task = asyncio.create_task(health_check())
    
    # Connect to server with retry mechanism
    retry_count = 0
    max_retries = 5
    
    while retry_count < max_retries and not sio.connected:
        try:
            logger.info(f"Connecting to server at {args.server} (attempt {retry_count + 1}/{max_retries})")
            await sio.connect(args.server)
            logger.info("Successfully connected to server")
        except Exception as e:
            retry_count += 1
            if retry_count < max_retries:
                wait_time = RECONNECT_DELAY * retry_count
                logger.warning(f"Failed to connect to server: {e}, retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Failed to connect to server after {max_retries} attempts: {e}")
                return
    
    # Keep the program running with graceful shutdown
    try:
        while running:
            await asyncio.sleep(1)
            """
            # Start real GPS task
            if gps_task_runner and not gps_task_runner.done():
                gps_task_runner.cancel()
            gps_task_runner = asyncio.create_task(gps_task(sio, device_id, device_name, serial_port="/dev/ttyAMA0", baudrate=9600, gps_interval=DEFAULT_GPS_INTERVAL))
            logger.info("Started real GPS task from module gps_utils")
            """
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down gracefully")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        # Perform cleanup
        await cleanup()
        logger.info("Shutdown complete")

nest_asyncio.apply()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("User stopped program")
    finally:
        loop.run_until_complete(asyncio.sleep(0.1))
        loop.close()
