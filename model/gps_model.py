import logging

logger = logging.getLogger(__name__)

class GPSData:
    def __init__(self, device_id, latitude, longitude, altitude=0, speed=0, timestamp=None):
        """
        Khởi tạo đối tượng dữ liệu GPS
        
        Args:
            device_id (str): ID của thiết bị (drone hoặc phao cứu hộ)
            latitude (float): Vĩ độ
            longitude (float): Kinh độ
            altitude (float, optional): Độ cao. Mặc định là 0.
            speed (float, optional): Tốc độ. Mặc định là 0.
            timestamp (float, optional): Thời gian. Mặc định là None.
        """
        self.device_id = device_id
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.speed = speed
        self.timestamp = timestamp
        logger.debug(f"[GPS MODEL] Created GPSData for device: {device_id}, lat: {latitude}, lon: {longitude}")
    
    def to_dict(self):
        """
        Chuyển đổi đối tượng thành dictionary để gửi qua WebSocket
        
        Returns:
            dict: Dictionary chứa dữ liệu GPS
        """
        return {
            'device_id': self.device_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'speed': self.speed,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data):
        """
        Tạo đối tượng GPSData từ dictionary
        
        Args:
            data (dict): Dictionary chứa dữ liệu GPS
            
        Returns:
            GPSData: Đối tượng GPSData mới
        """
        return cls(
            device_id=data.get('device_id'),
            latitude=data.get('latitude'),
            longitude=data.get('longitude'),
            altitude=data.get('altitude', 0),
            speed=data.get('speed', 0),
            timestamp=data.get('timestamp')
        )