import asyncio
import serial_asyncio
import pynmea2
from datetime import datetime
import logging


logger = logging.getLogger("drone-client")


async def read_gps(serial_port="/dev/ttyAMA3", baudrate=9600):
    """Async generator: yield GPS data dict from NMEA sentences"""
    reader, _ = await serial_asyncio.open_serial_connection(url=serial_port, baudrate=baudrate)
   
    while True:
        try:
            line = await reader.readline()
            line = line.decode("ascii", errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GPRMC"):
                msg = pynmea2.parse(line)
               
                # GPGGA contains lat/lon/altitude
                if hasattr(msg, "latitude") and hasattr(msg, "longitude"):
                    gps_data = {
                        "latitude": msg.latitude,
                        "longitude": msg.longitude,
                        "altitude": getattr(msg, "altitude", 0.0),
                        "speed": getattr(msg, "spd_over_grnd", 0.0),
                        "heading": getattr(msg, "true_course", 0.0),
                        "accuracy": getattr(msg, "horizontal_dil", 0.0),
                        "timestamp": datetime.now().isoformat(),
                    }
                    yield gps_data
        except Exception as e:
            logger.warning(f"GPS parse error: {e}")


async def gps_task(sio, device_id, device_name, serial_port="/dev/ttyAMA3", baudrate=9600, gps_interval=1.0):
    """Send real GPS data to server"""
    async for gps in read_gps(serial_port, baudrate):
        gps["device_id"] = device_id
        gps["device_name"] = device_name
        await sio.emit("gps_data", gps)
        logger.debug(f"Sent GPS data: {gps['latitude']:.6f}, {gps['longitude']:.6f}")
        await asyncio.sleep(gps_interval)
