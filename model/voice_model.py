"""
Database model for Voice Distress Records
Stores audio recordings with GPS location and AI analysis
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, JSON, Index
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class VoiceRecord(Base):
    """Model for voice distress records from rescue microphones"""
    __tablename__ = 'voice_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Location information
    device_id = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, default=0)
    
    # Audio information
    audio_url = Column(String(500), nullable=False)  # Cloudinary URL
    duration_seconds = Column(Integer, default=15)
    
    # Transcription (available immediately)
    transcribed_text = Column(Text, nullable=True)
    transcription_status = Column(String(50), default='pending')  # pending, completed, failed
    
    # AI Analysis (takes longer, updated later)
    analysis_intent = Column(String(100), nullable=True)  # Bị thương, Đói/Khát, Cứu Gấp, Không rõ
    analysis_items = Column(JSON, nullable=True)  # List of items needed
    analysis_status = Column(String(50), default='pending')  # pending, processing, completed, failed
    analysis_error = Column(Text, nullable=True)
    
    # Status tracking
    is_urgent = Column(Boolean, default=False)
    is_resolved = Column(Boolean, default=False)
    priority = Column(String(20), default='medium')  # low, medium, high, critical
    
    # Timestamps
    recorded_at = Column(DateTime, default=datetime.utcnow)
    transcribed_at = Column(DateTime, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # Notes from operators
    operator_notes = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<VoiceRecord(id={self.id}, device={self.device_id}, status={self.transcription_status}/{self.analysis_status})>"
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'id': self.id,
            'device_id': self.device_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'audio_url': self.audio_url,
            'duration_seconds': self.duration_seconds,
            'transcribed_text': self.transcribed_text,
            'transcription_status': self.transcription_status,
            'analysis_intent': self.analysis_intent,
            'analysis_items': self.analysis_items,
            'analysis_status': self.analysis_status,
            'analysis_error': self.analysis_error,
            'is_urgent': self.is_urgent,
            'is_resolved': self.is_resolved,
            'priority': self.priority,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'transcribed_at': self.transcribed_at.isoformat() if self.transcribed_at else None,
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'operator_notes': self.operator_notes
        }
