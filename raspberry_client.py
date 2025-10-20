#!/usr/bin/env python3
"""
Raspberry Pi client for Sky WebApp
Streams video via WebRTC and sends GPS data via WebSocket
"""

import argparse
import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime

import cv2
import numpy as np
import socketio
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay
from av import VideoFrame

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("raspberry-client")

# Default configuration
DEFAULT_SERVER_URL = "http://localhost:5000"
DEFAULT_DEVICE_ID = f"raspberry-{uuid.uuid4().hex[:8]}"
DEFAULT_DEVICE_NAME = "Raspberry Pi Camera"
DEFAULT_FPS = 30
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_GPS_INTERVAL = 1.0  # seconds

# Socket.IO client
sio = socketio.AsyncClient()

# Global variables
peer_connection = None
device_id = DEFAULT_DEVICE_ID
device_name = DEFAULT_DEVICE_NAME
relay = MediaRelay()
webcam = None
gps_task = None
running = True


class CameraStreamTrack(VideoStreamTrack):
    """
    Video stream track that captures from a camera
    """

    def __init__(self, camera, fps, width, height):
        super().__init__()
        self.camera = camera
        self.fps = fps
        self.width = width
        self.height = height
        self.counter = 0
        self.last_frame_time = time.time()

    async def recv(self):
        self.counter += 1
        
        # Limit frame rate
        now = time.time()
        elapsed = now - self.last_frame_time
        target_elapsed = 1.0 / self.fps
        if elapsed < target_elapsed:
            await asyncio.sleep(target_elapsed - elapsed)
        
        # Read frame from camera
        ret, frame = self.camera.read()
        if not ret:
            # If camera read fails, create a blank frame
            frame = np.zeros((self.height, self.width, 3), np.uint8)
            cv2.putText(
                frame, 
                "Camera Error", 
                (self.width // 4, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 
                1, 
                (255, 255, 255), 
                2
            )
        
        # Convert to VideoFrame
        frame = VideoFrame.from_ndarray(frame, format="bgr24")
        frame.pts = self.counter
        frame.time_base = 1 / self.fps
        self.last_frame_time = time.time()
        
        return frame


async def setup_camera(width, height, fps):
    """Set up the camera with specified parameters"""
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    camera.set(cv2.CAP_PROP_FPS, fps)
    
    if not camera.isOpened():
        logger.error("Failed to open camera")
        return None
    
    logger.info(f"Camera initialized: {width}x{height} @ {fps}fps")
    return camera


async def create_offer():
    """Create a WebRTC offer"""
    global peer_connection
    
    # Create a new RTCPeerConnection
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    peer_connection = RTCPeerConnection(config)
    
    # Add video track
    if webcam:
        video_track = CameraStreamTrack(webcam, DEFAULT_FPS, DEFAULT_WIDTH, DEFAULT_HEIGHT)
        peer_connection.addTrack(video_track)
    
    # Create offer
    offer = await peer_connection.createOffer()
    await peer_connection.setLocalDescription(offer)
    
    # Return the SDP offer
    return {
        "sdp": peer_connection.localDescription.sdp,
        "type": peer_connection.localDescription.type,
    }


async def simulate_gps_data():
    """Simulate GPS data (in a real scenario, this would read from a GPS module)"""
    # Starting position (can be customized)
    lat = 10.762622
    lng = 106.660172
    
    while running:
        # Simulate movement
        lat += (np.random.random() - 0.5) * 0.0001
        lng += (np.random.random() - 0.5) * 0.0001
        
        # Create GPS data
        gps_data = {
            "device_id": device_id,
            "device_name": device_name,
            "latitude": lat,
            "longitude": lng,
            "altitude": 10 + np.random.random() * 5,
            "speed": 5 + np.random.random() * 10,
            "heading": np.random.random() * 360,
            "accuracy": 2 + np.random.random() * 3,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Send GPS data to server
        await sio.emit("gps_data", gps_data)
        logger.debug(f"Sent GPS data: {lat:.6f}, {lng:.6f}")
        
        # Wait for next update
        await asyncio.sleep(DEFAULT_GPS_INTERVAL)


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
    
    # Start GPS data simulation
    global gps_task
    gps_task = asyncio.create_task(simulate_gps_data())


@sio.event
async def disconnect():
    """Handle Socket.IO disconnection"""
    logger.info("Disconnected from server")
    
    # Stop GPS task if running
    global gps_task
    if gps_task:
        gps_task.cancel()
        gps_task = None


@sio.on("webrtc_request")
async def on_webrtc_request(data):
    """Handle WebRTC request from server"""
    logger.info(f"Received WebRTC request for device {data.get('device_id')}")
    
    # Check if the request is for this device
    if data.get("device_id") == device_id:
        # Create and send offer
        offer = await create_offer()
        await sio.emit(
            "webrtc_offer",
            {"device_id": device_id, "sdp": offer["sdp"], "type": offer["type"]},
        )


@sio.on("webrtc_answer")
async def on_webrtc_answer(data):
    """Handle WebRTC answer from server"""
    global peer_connection
    
    # Check if the answer is for this device
    if data.get("device_id") == device_id and peer_connection:
        logger.info("Received WebRTC answer")
        
        # Set remote description
        answer = RTCSessionDescription(sdp=data["sdp"], type=data["type"])
        await peer_connection.setRemoteDescription(answer)


@sio.on("webrtc_ice_candidate")
async def on_ice_candidate(data):
    """Handle ICE candidate from server"""
    global peer_connection
    
    # Check if the ICE candidate is for this device
    if data.get("device_id") == device_id and peer_connection:
        logger.debug("Received ICE candidate")
        
        # Add ICE candidate
        candidate = data.get("candidate")
        if candidate:
            await peer_connection.addIceCandidate(candidate)


async def main():
    """Main function"""
    global webcam, device_id, device_name, running
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Raspberry Pi client for Sky WebApp")
    parser.add_argument(
        "--server-url",
        type=str,
        default=DEFAULT_SERVER_URL,
        help=f"Server URL (default: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--device-id",
        type=str,
        default=DEFAULT_DEVICE_ID,
        help=f"Device ID (default: {DEFAULT_DEVICE_ID})",
    )
    parser.add_argument(
        "--device-name",
        type=str,
        default=DEFAULT_DEVICE_NAME,
        help=f"Device name (default: {DEFAULT_DEVICE_NAME})",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Camera FPS (default: {DEFAULT_FPS})",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help=f"Camera width (default: {DEFAULT_WIDTH})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_HEIGHT,
        help=f"Camera height (default: {DEFAULT_HEIGHT})",
    )
    parser.add_argument(
        "--gps-interval",
        type=float,
        default=DEFAULT_GPS_INTERVAL,
        help=f"GPS update interval in seconds (default: {DEFAULT_GPS_INTERVAL})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()
    
    # Set logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    # Set global variables
    device_id = args.device_id
    device_name = args.device_name
    
    # Initialize camera
    webcam = await setup_camera(args.width, args.height, args.fps)
    if not webcam:
        logger.error("Failed to initialize camera, exiting")
        return
    
    try:
        # Connect to server
        logger.info(f"Connecting to server at {args.server_url}")
        await sio.connect(args.server_url)
        
        # Keep running until interrupted
        while running:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    
    except Exception as e:
        logger.error(f"Error: {e}")
    
    finally:
        # Clean up
        running = False
        
        if webcam:
            webcam.release()
        
        if peer_connection:
            await peer_connection.close()
        
        if sio.connected:
            await sio.disconnect()
        
        logger.info("Client stopped")


if __name__ == "__main__":
    asyncio.run(main())