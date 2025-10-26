import asyncio
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger("drone-client")

async def simulate_gps_data(sio, device_id, device_name, running, gps_interval=1.0):
    """Simulate GPS data for computer (temporarily)"""
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
        await asyncio.sleep(gps_interval)