class VideoStream:
    def __init__(self, device_id, stream_url=None, webrtc_config=None):
        """
        Khởi tạo đối tượng VideoStream
        
        Args:
            device_id (str): ID của thiết bị (Raspberry Pi)
            stream_url (str, optional): URL của stream video. Mặc định là None.
            webrtc_config (dict, optional): Cấu hình WebRTC. Mặc định là None.
        """
        self.device_id = device_id
        self.stream_url = stream_url
        self.webrtc_config = webrtc_config or {}
        self.is_active = False
    
    def to_dict(self):
        """
        Chuyển đổi đối tượng thành dictionary
        
        Returns:
            dict: Dictionary chứa thông tin stream video
        """
        return {
            'device_id': self.device_id,
            'stream_url': self.stream_url,
            'is_active': self.is_active
        }
    
    @classmethod
    def from_dict(cls, data):
        """
        Tạo đối tượng VideoStream từ dictionary
        
        Args:
            data (dict): Dictionary chứa thông tin stream video
            
        Returns:
            VideoStream: Đối tượng VideoStream mới
        """
        stream = cls(
            device_id=data.get('device_id'),
            stream_url=data.get('stream_url'),
            webrtc_config=data.get('webrtc_config')
        )
        stream.is_active = data.get('is_active', False)
        return stream