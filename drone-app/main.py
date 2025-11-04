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
from datetime import datetime
import nest_asyncio

import cv2
import numpy as np
import socketio
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
from detection_utils import (
    periodic_report_task, on_demand_report,
    set_report_interval, enable_periodic_report, disable_periodic_report,
    is_periodic_report_enabled, get_report_interval,
    set_detection_camera, detect_objects_from_camera, get_latest_detection
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("drone-client")

# Default configuration
DEFAULT_SERVER_URL = "https://popular-catfish-slightly.ngrok-free.app"
DEFAULT_DEVICE_ID = "drone-camera"  # Fixed device ID for easier debugging
DEFAULT_DEVICE_NAME = "Drone Camera"
DEFAULT_FPS = 15
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
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
last_detection_emit_time = 0  # Throttle detection data emission
report_task_runner = None  # Periodic report task
detection_task_runner = None  # Continuous detection task for real-time updates


def send_detection_data(detection_data):
    """Callback function to send detection data via Socket.IO"""
    global last_detection_emit_time
    
    # Throttle emissions to every 2 seconds
    current_time = time.time()
    if current_time - last_detection_emit_time < 2:
        return
    
    last_detection_emit_time = current_time
    
    # Prepare data to send
    data_to_send = {
        "device_id": device_id,
        "device_name": device_name,
        "earth_person": detection_data["earth_person"],
        "sea_person": detection_data["sea_person"],
        "total": detection_data["total"],
        "timestamp": datetime.now().isoformat(),
        "detections": detection_data.get("detections", [])
    }
    
    # Emit asynchronously
    asyncio.create_task(sio.emit("detection_data", data_to_send))


async def continuous_detection_task():
    """
    Continuous task to run detection and send real-time updates
    Automatically switches between video_track buffer and direct camera
    """
    global running, last_detection_emit_time, video_track
    
    logger.info("Continuous detection task started, waiting for setup...")
    
    # Wait for video_track to be ready AND detection to be setup
    logger.info("Waiting for video_track and detection setup...")
    wait_count = 0
    max_wait = 60  # Wait up to 60 seconds
    
    while running and wait_count < max_wait:
        if video_track and video_track.is_active():
            # Check if detection is setup by trying to get frame buffer
            try:
                frame = video_track.frame_buffer.get_latest_frame()
                if frame is not None:
                    logger.info("Video track and detection are ready!")
                    break
            except:
                pass
        
        await asyncio.sleep(1)
        wait_count += 1
    
    if wait_count >= max_wait:
        logger.warning("Timeout waiting for video_track, will try direct camera fallback")
    
    logger.info("Starting detection loop (with automatic camera fallback)...")
    
    failed_count = 0
    max_failed = 10  # If detection fails 10 times in a row, wait longer
    
    while running:
        try:
            # Run detection - automatically switches between video_track and direct camera
            frame, detection_data = detect_objects_from_camera()
            
            if detection_data:
                # Send detection data (with throttling)
                send_detection_data(detection_data)
                failed_count = 0  # Reset failed counter on success
            else:
                failed_count += 1
            
            # Adaptive sleep: wait longer if detection is failing
            if failed_count >= max_failed:
                await asyncio.sleep(2)  # Wait longer when failing
            else:
                await asyncio.sleep(0.5)  # Normal: 2 FPS for detection
            
        except asyncio.CancelledError:
            logger.info("Continuous detection task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in continuous detection task: {e}", exc_info=True)
            await asyncio.sleep(1)  # Wait before retrying
    logger.debug(f"Sent detection data: Earth={detection_data['earth_person']}, Sea={detection_data['sea_person']}")


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
        logger.info(f"ICE connection state: {peer_connection.iceConnectionState}")
    
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
            video_track = ObjectDetectionStreamTrack(
                webcam, DEFAULT_FPS, DEFAULT_WIDTH, DEFAULT_HEIGHT, 
                ort_session, detection_callback=send_detection_data
            )
            
            # Set detection camera reference (share webcam and video_track, no separate camera)
            if ort_session:
                set_detection_camera(webcam, ort_session, video_track)
                logger.info("Detection setup complete - sharing camera with WebRTC (no conflict)")
        
        peer_connection.addTrack(video_track)
        logger.info("Added video track to peer connection")
    else:
        logger.warning("No webcam available, cannot add video track")
    
    return peer_connection


async def create_offer():
    """Create a WebRTC offer with proper ICE gathering"""
    global peer_connection
    
    # Ensure we have a peer connection
    if not peer_connection:
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


async def restart_webrtc():
    """Restart the WebRTC connection"""
    logger.info("Restarting WebRTC connection")
    
    try:
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


@sio.event
async def connect():
    """Handle Socket.IO connection"""
    global gps_task_runner, report_task_runner, detection_task_runner, running
    
    logger.info(f"Connected to server as {device_id}")
    
    # Register device
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
    
    
    # Start real GPS task
    if gps_task_runner and not gps_task_runner.done():
        gps_task_runner.cancel()
    gps_task_runner = asyncio.create_task(
        gps_task(sio, device_id, device_name, serial_port="/dev/ttyAMA0", baudrate=9600, gps_interval=DEFAULT_GPS_INTERVAL)
    )
    logger.info("Started GPS task")
    
    # Wait for video_track to be created (max 5 seconds)
    wait_count = 0
    while video_track is None and wait_count < 50:
        await asyncio.sleep(0.1)
        wait_count += 1
    
    if video_track is None:
        logger.warning("Video track not ready after 5 seconds, detection tasks may not work properly")
    else:
        logger.info("Video track is ready, starting detection tasks")
    
    # Start periodic report task (uses video_track buffer)
    if report_task_runner and not report_task_runner.done():
        report_task_runner.cancel()
    report_task_runner = asyncio.create_task(
        periodic_report_task(sio, device_id, device_name, video_track=None)
    )
    logger.info("Started periodic detection report task")
    
    # Start continuous detection task for real-time updates
    if detection_task_runner and not detection_task_runner.done():
        detection_task_runner.cancel()
    detection_task_runner = asyncio.create_task(continuous_detection_task())
    logger.info("Started continuous detection task")


@sio.event
async def disconnect():
    """Handle Socket.IO disconnection"""
    global gps_task_runner, report_task_runner
    
    logger.info("Disconnected from server")
    
    # Don't set running to False here to allow reconnection
    # Just cancel the tasks, they will be restarted on reconnect
    if gps_task_runner and not gps_task_runner.done():
        gps_task_runner.cancel()
    
    if report_task_runner and not report_task_runner.done():
        report_task_runner.cancel()


@sio.event
async def webrtc_offer(data):
    """Handle incoming WebRTC offer from frontend"""
    # In our optimized design, the drone is always the offerer
    # We'll log this but ignore it to prevent negotiation glare
    logger.info("Received webrtc_offer from frontend, but drone is configured as offerer")


@sio.event
async def webrtc_answer(data):
    """Handle WebRTC answer from server"""
    try:
        if peer_connection:
            answer = RTCSessionDescription(sdp=data['sdp'], type=data['type'])
            await peer_connection.setRemoteDescription(answer)
            logger.info("WebRTC answer received and set successfully")
        else:
            logger.error("Received webrtc_answer but no peer connection exists")
    except Exception as e:
        logger.error(f"Error setting remote description: {e}")
        # Try to recover by restarting WebRTC
        await asyncio.sleep(1)
        await restart_webrtc()


@sio.event
async def webrtc_ice_candidate(data):
    """Handle ICE candidate from server"""
    try:
        if peer_connection and peer_connection.connectionState != "closed":
            candidate = RTCIceCandidate(
                data['candidate']['candidate'],
                sdpMid=data['candidate'].get('sdpMid'),
                sdpMLineIndex=data['candidate'].get('sdpMLineIndex'),
            )
            await peer_connection.addIceCandidate(candidate)
            logger.debug(f"Added remote ICE candidate: {candidate.candidate}")
        else:
            logger.warning("Received ICE candidate but peer connection is not available")
    except Exception as e:
        logger.error(f"Error adding ICE candidate: {e}")


@sio.event
async def request_detection_report(data):
    """Handle request for on-demand detection report"""
    try:
        logger.info("Received request for detection report")
        success = await on_demand_report(sio, device_id, device_name, video_track)
        if success:
            await sio.emit('report_status', {'status': 'success', 'device_id': device_id})
        else:
            await sio.emit('report_status', {'status': 'failed', 'device_id': device_id})
    except Exception as e:
        logger.error(f"Error generating on-demand report: {e}")
        await sio.emit('report_status', {'status': 'error', 'device_id': device_id, 'error': str(e)})


@sio.event
async def set_report_interval_event(data):
    """Handle request to change report interval"""
    try:
        interval = data.get('interval', 60)
        if interval < 60:
            interval = 60  # Minimum 1 minute
        
        set_report_interval(interval)
        
        await sio.emit('report_config_updated', {
            'status': 'success',
            'device_id': device_id,
            'interval': interval,
            'enabled': is_periodic_report_enabled()
        })
        logger.info(f"Report interval updated to {interval} seconds")
    except Exception as e:
        logger.error(f"Error setting report interval: {e}")
        await sio.emit('report_config_updated', {
            'status': 'error',
            'device_id': device_id,
            'error': str(e)
        })


@sio.event
async def toggle_periodic_report(data):
    """Handle request to enable/disable periodic reporting"""
    try:
        enabled = data.get('enabled', True)
        
        if enabled:
            enable_periodic_report()
        else:
            disable_periodic_report()
        
        await sio.emit('report_config_updated', {
            'status': 'success',
            'device_id': device_id,
            'enabled': is_periodic_report_enabled(),
            'interval': get_report_interval()
        })
        logger.info(f"Periodic reporting {'enabled' if enabled else 'disabled'}")
    except Exception as e:
        logger.error(f"Error toggling periodic report: {e}")
        await sio.emit('report_config_updated', {
            'status': 'error',
            'device_id': device_id,
            'error': str(e)
        })


async def health_check():
    """Periodic health check for WebRTC connection"""
    while running:
        try:
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
    global running, peer_connection, webcam, video_track, gps_task_runner, report_task_runner
    
    running = False
    
    # Cancel tasks
    if gps_task_runner and not gps_task_runner.done():
        gps_task_runner.cancel()
    
    if report_task_runner and not report_task_runner.done():
        report_task_runner.cancel()
    
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
    
    # Disconnect from server
    if sio.connected:
        await sio.disconnect()


async def main():
    """Main function"""
    global webcam, ort_session, running, device_id, device_name, gps_task_runner, running
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Drone App Client")
    parser.add_argument("--server", default=DEFAULT_SERVER_URL, help="Server URL")
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="Device ID")
    parser.add_argument("--device-name", default=DEFAULT_DEVICE_NAME, help="Device name")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Video width")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Video height")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="Video FPS")
    parser.add_argument("--model", default="model_fp32.onnx", help="Path to ONNX model")
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
    
    # Setup camera with retry mechanism (for WebRTC)
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries and not webcam:
        logger.info(f"Setting up WebRTC camera (attempt {retry_count + 1}/{max_retries})")
        webcam = await setup_camera(args.width, args.height, args.fps)
        
        if not webcam:
            retry_count += 1
            if retry_count < max_retries:
                logger.warning(f"Failed to setup WebRTC camera, retrying in 2 seconds...")
                await asyncio.sleep(2)
            else:
                logger.error("Failed to setup WebRTC camera after multiple attempts")
                return
    
    logger.info("WebRTC camera setup successful")
    
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
