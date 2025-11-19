"""
Capture Record Model - Store image capture with AI analysis results
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class CaptureRecord(Base):
    """Model for storing captured images with AI analysis"""
    __tablename__ = 'capture_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(100), nullable=False, index=True)
    
    # Image URLs
    original_image_url = Column(Text, nullable=False)  # URL from Cloudinary
    analyzed_image_url = Column(Text, nullable=True)   # URL after AI analysis
    
    # GPS data
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    
    # AI Analysis results
    person_count = Column(Integer, default=0)
    earth_person_count = Column(Integer, default=0)
    sea_person_count = Column(Integer, default=0)
    
    # Status
    analysis_status = Column(String(50), default='pending')  # pending, processing, completed, failed
    
    # Timestamps
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'device_id': self.device_id,
            'original_image_url': self.original_image_url,
            'analyzed_image_url': self.analyzed_image_url,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'person_count': self.person_count,
            'earth_person_count': self.earth_person_count,
            'sea_person_count': self.sea_person_count,
            'analysis_status': self.analysis_status,
            'captured_at': self.captured_at.isoformat() if self.captured_at else None,
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
