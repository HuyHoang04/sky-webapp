"""
Database model for Image Capture Records
Stores captured images with GPS location and AI analysis results
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.sql import func
from database import Base
from datetime import datetime, timezone

class CaptureRecord(Base):
    """Model for image capture records from drone camera"""
    __tablename__ = 'capture_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Location information
    device_id = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, default=0)
    
    # Image information
    image_url = Column(String(500), nullable=False)  # Original image URL (Cloudinary)
    
    # AI Analysis results
    analyzed_image_url = Column(String(500), nullable=True)  # Image with bounding boxes (Cloudinary)
    total_person_count = Column(Integer, default=0)
    earth_person_count = Column(Integer, default=0)
    sea_person_count = Column(Integer, default=0)
    detections = Column(JSON, nullable=True)  # List of detection objects
    analysis_status = Column(String(50), default='pending')  # pending, processing, completed, failed
    analysis_error = Column(Text, nullable=True)
    
    # Status tracking
    is_urgent = Column(Boolean, default=False)
    is_resolved = Column(Boolean, default=False)
    priority = Column(String(20), default='medium')  # low, medium, high, critical
    
    # Timestamps (timezone-aware)
    captured_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    analyzed_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notes from operators
    operator_notes = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<CaptureRecord(id={self.id}, device={self.device_id}, status={self.analysis_status}, persons={self.total_person_count})>"
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'device_id': self.device_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'image_url': self.image_url,
            'analyzed_image_url': self.analyzed_image_url,
            'total_person_count': self.total_person_count,
            'earth_person_count': self.earth_person_count,
            'sea_person_count': self.sea_person_count,
            'detections': self.detections,
            'analysis_status': self.analysis_status,
            'analysis_error': self.analysis_error,
            'is_urgent': self.is_urgent,
            'is_resolved': self.is_resolved,
            'priority': self.priority,
            'captured_at': self.captured_at.isoformat() if self.captured_at else None,
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'operator_notes': self.operator_notes
        }
