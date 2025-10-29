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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("drone-client")

# Default configuration
DEFAULT_SERVER_URL = "https://kanisha-unannexable-laraine.ngrok-free.dev"
DEFAULT_DEVICE_ID = "drone-camera"  # Fixed device ID for easier debugging
DEFAULT_DEVICE_NAME = "Drone Camera"
DEFAULT_FPS = 30
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
            video_track = ObjectDetectionStreamTrack(webcam, DEFAULT_FPS, DEFAULT_WIDTH, DEFAULT_HEIGHT, ort_session)
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
    global gps_task_runner, running
    if gps_task_runner and not gps_task_runner.done():
        gps_task.cancel()
    gps_task_runner = asyncio.create_task(gps_task(sio, device_id, device_name, serial_port="/dev/ttyAMA0", baudrate=9600, gps_interval=DEFAULT_GPS_INTERVAL))
    logger.info("Started real GPS task from module gps_utils")


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
                sdpMid=data['candidate'].get('sdpMid'),
                sdpMLineIndex=data['candidate'].get('sdpMLineIndex'),
                candidate=data['candidate']['candidate']
            )
            await peer_connection.addIceCandidate(candidate)
            logger.debug(f"Added remote ICE candidate: {candidate.candidate}")
        else:
            logger.warning("Received ICE candidate but peer connection is not available")
    except Exception as e:
        logger.error(f"Error adding ICE candidate: {e}")


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
    global running, peer_connection, webcam, video_track
    
    running = False
    
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
    
    # Disconnect from server
    if sio.connected:
        await sio.disconnect()


async def main():
    """Main function"""
    global webcam, ort_session, running, device_id, device_name
    
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
