from datetime import datetime
import sqlite3
import os
import json
from typing import List, Dict, Optional

# Database file path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'detection_data.db')

class DetectionData:
    """Model for real-time detection data"""
    def __init__(self, device_id, device_name, earth_person, sea_person, total, timestamp, detections=None):
        self.device_id = device_id
        self.device_name = device_name
        self.earth_person = earth_person
        self.sea_person = sea_person
        self.total = total
        self.timestamp = timestamp
        self.detections = detections or []
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            device_id=data.get('device_id'),
            device_name=data.get('device_name', 'Unknown'),
            earth_person=data.get('earth_person', 0),
            sea_person=data.get('sea_person', 0),
            total=data.get('total', 0),
            timestamp=data.get('timestamp'),
            detections=data.get('detections', [])
        )
    
    def to_dict(self):
        return {
            'device_id': self.device_id,
            'device_name': self.device_name,
            'earth_person': self.earth_person,
            'sea_person': self.sea_person,
            'total': self.total,
            'timestamp': self.timestamp,
            'detections': self.detections
        }


class DetectionReport:
    """Model for saved detection reports with images"""
    
    def __init__(self, device_id, device_name, earth_person_count, sea_person_count, 
                 total_count, image_data, timestamp=None, id=None):
        self.id = id
        self.device_id = device_id
        self.device_name = device_name
        self.earth_person_count = earth_person_count
        self.sea_person_count = sea_person_count
        self.total_count = total_count
        self.image_data = image_data  # Base64 encoded image
        self.timestamp = timestamp or datetime.now()
    
    @staticmethod
    def init_db():
        """Initialize database table"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detection_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                earth_person_count INTEGER DEFAULT 0,
                sea_person_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                image_data TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_device_timestamp 
            ON detection_reports(device_id, timestamp DESC)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON detection_reports(timestamp DESC)
        ''')
        
        conn.commit()
        conn.close()
    
    def save(self):
        """Save detection report to database"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO detection_reports 
            (device_id, device_name, earth_person_count, sea_person_count, 
             total_count, image_data, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.device_id,
            self.device_name,
            self.earth_person_count,
            self.sea_person_count,
            self.total_count,
            self.image_data,
            self.timestamp
        ))
        
        self.id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return self.id
    
    @staticmethod
    def get_by_id(report_id: int) -> Optional['DetectionReport']:
        """Get detection report by ID"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, device_id, device_name, earth_person_count, sea_person_count,
                   total_count, image_data, timestamp
            FROM detection_reports
            WHERE id = ?
        ''', (report_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return DetectionReport(
                id=row[0],
                device_id=row[1],
                device_name=row[2],
                earth_person_count=row[3],
                sea_person_count=row[4],
                total_count=row[5],
                image_data=row[6],
                timestamp=datetime.fromisoformat(row[7]) if row[7] else None
            )
        return None
    
    @staticmethod
    def get_recent_reports(limit: int = 50, device_id: Optional[str] = None) -> List['DetectionReport']:
        """Get recent detection reports"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if device_id:
            cursor.execute('''
                SELECT id, device_id, device_name, earth_person_count, sea_person_count,
                       total_count, image_data, timestamp
                FROM detection_reports
                WHERE device_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (device_id, limit))
        else:
            cursor.execute('''
                SELECT id, device_id, device_name, earth_person_count, sea_person_count,
                       total_count, image_data, timestamp
                FROM detection_reports
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        reports = []
        for row in rows:
            reports.append(DetectionReport(
                id=row[0],
                device_id=row[1],
                device_name=row[2],
                earth_person_count=row[3],
                sea_person_count=row[4],
                total_count=row[5],
                image_data=row[6],
                timestamp=datetime.fromisoformat(row[7]) if row[7] else None
            ))
        
        return reports
    
    @staticmethod
    def get_statistics(device_id: Optional[str] = None) -> Dict:
        """Get detection statistics"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if device_id:
            # Stats for specific device
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_reports,
                    AVG(earth_person_count) as avg_earth,
                    AVG(sea_person_count) as avg_sea,
                    AVG(total_count) as avg_total,
                    MAX(total_count) as max_total,
                    MIN(timestamp) as first_report,
                    MAX(timestamp) as last_report
                FROM detection_reports
                WHERE device_id = ?
            ''', (device_id,))
        else:
            # Overall stats
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_reports,
                    AVG(earth_person_count) as avg_earth,
                    AVG(sea_person_count) as avg_sea,
                    AVG(total_count) as avg_total,
                    MAX(total_count) as max_total,
                    MIN(timestamp) as first_report,
                    MAX(timestamp) as last_report
                FROM detection_reports
            ''')
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'total_reports': row[0] or 0,
            'avg_earth_person': round(row[1], 2) if row[1] else 0,
            'avg_sea_person': round(row[2], 2) if row[2] else 0,
            'avg_total': round(row[3], 2) if row[3] else 0,
            'max_total': row[4] or 0,
            'first_report': row[5],
            'last_report': row[6]
        }
    
    @staticmethod
    def delete_old_reports(days: int = 30):
        """Delete reports older than specified days"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM detection_reports
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        ''', (days,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def to_dict(self, include_image=False):
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'earth_person_count': self.earth_person_count,
            'sea_person_count': self.sea_person_count,
            'total_count': self.total_count,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
        
        if include_image:
            data['image_data'] = self.image_data
        
        return data


# Initialize database on module import
DetectionReport.init_db()
