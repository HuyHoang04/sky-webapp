"""
Database models for Mission, Waypoint, Route, and Order management
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, 
    ForeignKey, Enum, Text, JSON, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum
from datetime import datetime

# ============================================
# ENUMERATIONS
# ============================================

class MissionType(enum.Enum):
    """Mission type categories"""
    SURVEY = "survey"
    INSPECTION = "inspection"
    DELIVERY = "delivery"
    PATROL = "patrol"
    EMERGENCY = "emergency"
    MAPPING = "mapping"

class MissionStatus(enum.Enum):
    """Mission execution status"""
    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

class OrderCategory(enum.Enum):
    """Order delivery categories"""
    FOOD = "food"
    MEDICAL = "medical"
    EQUIPMENT = "equipment"
    DOCUMENTS = "documents"
    EMERGENCY = "emergency"
    OTHER = "other"

class OrderPriority(enum.Enum):
    """Order delivery priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class OrderStatus(enum.Enum):
    """Order fulfillment status"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"

class WaypointType(enum.Enum):
    """Waypoint types"""
    POINT = "point"
    PICKUP = "pickup"
    DELIVERY = "delivery"
    TAKEOFF = "takeoff"
    LANDING = "landing"
    HOME = "home"

# ============================================
# MISSION MODEL
# ============================================

class Mission(Base):
    """
    Main mission model for flight planning and execution
    Stores configuration, parameters, and metadata for drone missions
    """
    __tablename__ = "missions"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic Information
    name = Column(String(255), nullable=False)
    mission_type = Column(Enum(MissionType), nullable=False, index=True)
    status = Column(Enum(MissionStatus), default=MissionStatus.DRAFT, index=True)
    
    # Device Information
    device_id = Column(String(100), nullable=False, index=True)
    device_name = Column(String(255))
    
    # Flight Parameters
    flight_height = Column(Float, default=50.0, comment="Flight altitude in meters")
    flight_speed = Column(Float, default=5.0, comment="Flight speed in m/s")
    return_altitude = Column(Float, default=70.0, comment="Return to home altitude in meters")
    
    # Mission Configuration
    photo_interval = Column(Float, default=2.0, comment="Photo capture interval in seconds")
    overlap = Column(Float, default=75.0, comment="Photo overlap percentage")
    camera_angle = Column(Float, default=90.0, comment="Camera angle in degrees (90=straight down)")
    
    # Safety Settings
    min_battery = Column(Float, default=30.0, comment="Minimum battery percentage for RTH")
    max_distance = Column(Float, default=2000.0, comment="Maximum distance from home in meters")
    obstacle_avoidance = Column(Boolean, default=True)
    geofencing = Column(Boolean, default=True)
    emergency_rth = Column(Boolean, default=True, comment="Emergency return to home enabled")
    
    # Mission Statistics (calculated)
    total_distance = Column(Float, default=0.0, comment="Total mission distance in kilometers")
    estimated_duration = Column(Integer, default=0, comment="Estimated duration in seconds")
    battery_required = Column(Float, default=0.0, comment="Estimated battery usage percentage")
    photos_estimated = Column(Integer, default=0)
    waypoint_count = Column(Integer, default=0)
    
    # Scheduling
    scheduled_start = Column(DateTime(timezone=True))
    scheduled_end = Column(DateTime(timezone=True))
    actual_start = Column(DateTime(timezone=True))
    actual_end = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Additional Information
    description = Column(Text)
    notes = Column(Text)
    custom_data = Column(JSON, default={}, comment="Additional custom data")
    
    # Relationships
    waypoints = relationship("Waypoint", back_populates="mission", cascade="all, delete-orphan", order_by="Waypoint.sequence")
    routes = relationship("Route", back_populates="mission", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="mission", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('ix_mission_device_status', 'device_id', 'status'),
        Index('ix_mission_type_status', 'mission_type', 'status'),
    )
    
    def to_dict(self):
        """Convert mission to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'mission_type': self.mission_type.value if self.mission_type else None,
            'status': self.status.value if self.status else None,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'flight_height': self.flight_height,
            'flight_speed': self.flight_speed,
            'return_altitude': self.return_altitude,
            'photo_interval': self.photo_interval,
            'overlap': self.overlap,
            'camera_angle': self.camera_angle,
            'min_battery': self.min_battery,
            'max_distance': self.max_distance,
            'obstacle_avoidance': self.obstacle_avoidance,
            'geofencing': self.geofencing,
            'emergency_rth': self.emergency_rth,
            'total_distance': self.total_distance,
            'estimated_duration': self.estimated_duration,
            'battery_required': self.battery_required,
            'photos_estimated': self.photos_estimated,
            'waypoint_count': self.waypoint_count,
            'scheduled_start': self.scheduled_start.isoformat() if self.scheduled_start else None,
            'scheduled_end': self.scheduled_end.isoformat() if self.scheduled_end else None,
            'actual_start': self.actual_start.isoformat() if self.actual_start else None,
            'actual_end': self.actual_end.isoformat() if self.actual_end else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'description': self.description,
            'notes': self.notes,
            'custom_data': self.custom_data,
            'waypoints': [wp.to_dict() for wp in self.waypoints] if self.waypoints else [],
            'orders': [order.to_dict() for order in self.orders] if self.orders else []
        }
    
    def __repr__(self):
        return f"<Mission(id={self.id}, name='{self.name}', status='{self.status.value}')>"

# ============================================
# WAYPOINT MODEL
# ============================================

class Waypoint(Base):
    """
    Waypoint model for defining points in a mission path
    Can represent navigation points, pickup/delivery locations, etc.
    """
    __tablename__ = "waypoints"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key
    mission_id = Column(Integer, ForeignKey('missions.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Waypoint Details
    sequence = Column(Integer, nullable=False, comment="Order in mission (1, 2, 3...)")
    name = Column(String(255))
    waypoint_type = Column(Enum(WaypointType), default=WaypointType.POINT)
    
    # Coordinates
    latitude = Column(Float, nullable=False, comment="Latitude in decimal degrees")
    longitude = Column(Float, nullable=False, comment="Longitude in decimal degrees")
    altitude = Column(Float, default=0.0, comment="Altitude in meters above ground")
    
    # Actions at Waypoint
    action = Column(String(100), comment="Action to perform: hover, photo, drop_package, etc.")
    action_params = Column(JSON, default={}, comment="Parameters for the action")
    hover_time = Column(Float, default=0.0, comment="Hover duration in seconds")
    
    # Status Tracking
    reached = Column(Boolean, default=False)
    reached_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Additional Data
    notes = Column(Text)
    custom_data = Column(JSON, default={})
    
    # Relationships
    mission = relationship("Mission", back_populates="waypoints")
    
    # Indexes
    __table_args__ = (
        Index('ix_waypoint_mission_sequence', 'mission_id', 'sequence'),
    )
    
    def to_dict(self):
        """Convert waypoint to dictionary"""
        return {
            'id': self.id,
            'mission_id': self.mission_id,
            'sequence': self.sequence,
            'name': self.name,
            'waypoint_type': self.waypoint_type.value if self.waypoint_type else None,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'action': self.action,
            'action_params': self.action_params,
            'hover_time': self.hover_time,
            'reached': self.reached,
            'reached_at': self.reached_at.isoformat() if self.reached_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notes': self.notes,
            'custom_data': self.custom_data
        }
    
    def __repr__(self):
        return f"<Waypoint(id={self.id}, mission_id={self.mission_id}, sequence={self.sequence})>"

# ============================================
# ROUTE MODEL
# ============================================

class Route(Base):
    """
    Route model for storing optimized paths between waypoints
    Stores the calculated path with distance and time estimates
    """
    __tablename__ = "routes"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Keys
    mission_id = Column(Integer, ForeignKey('missions.id', ondelete='CASCADE'), nullable=False, index=True)
    from_waypoint_id = Column(Integer, ForeignKey('waypoints.id', ondelete='SET NULL'))
    to_waypoint_id = Column(Integer, ForeignKey('waypoints.id', ondelete='SET NULL'))
    
    # Path Data
    coordinates = Column(JSON, comment="Array of {lat, lng, alt} coordinate objects")
    
    # Route Statistics
    distance = Column(Float, comment="Route distance in meters")
    estimated_time = Column(Integer, comment="Estimated flight time in seconds")
    
    # Optimization Metrics
    cost = Column(Float, comment="Combined cost for optimization (distance + time + priority)")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    mission = relationship("Mission", back_populates="routes")
    
    def to_dict(self):
        """Convert route to dictionary"""
        return {
            'id': self.id,
            'mission_id': self.mission_id,
            'from_waypoint_id': self.from_waypoint_id,
            'to_waypoint_id': self.to_waypoint_id,
            'coordinates': self.coordinates,
            'distance': self.distance,
            'estimated_time': self.estimated_time,
            'cost': self.cost,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<Route(id={self.id}, mission_id={self.mission_id}, distance={self.distance}m)>"

# ============================================
# ORDER MODEL
# ============================================

class Order(Base):
    """
    Order model for delivery missions
    Tracks packages from pickup to delivery with full details
    """
    __tablename__ = "orders"
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key
    mission_id = Column(Integer, ForeignKey('missions.id', ondelete='CASCADE'), index=True)
    
    # Order Identification
    order_number = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(Enum(OrderCategory), nullable=False, index=True)
    priority = Column(Enum(OrderPriority), default=OrderPriority.MEDIUM, index=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    
    # Pickup Location
    pickup_latitude = Column(Float, nullable=False)
    pickup_longitude = Column(Float, nullable=False)
    pickup_address = Column(Text)
    pickup_contact_name = Column(String(255))
    pickup_contact_phone = Column(String(50))
    
    # Delivery Location
    delivery_latitude = Column(Float, nullable=False)
    delivery_longitude = Column(Float, nullable=False)
    delivery_address = Column(Text)
    delivery_contact_name = Column(String(255))
    delivery_contact_phone = Column(String(50))
    
    # Package Details
    package_weight = Column(Float, comment="Package weight in kg")
    package_dimensions = Column(JSON, comment="{length, width, height} in cm")
    items = Column(JSON, default=[], comment="List of items in the order")
    item_count = Column(Integer, default=1)
    
    # Special Requirements
    temperature_controlled = Column(Boolean, default=False)
    temperature_range = Column(String(50), comment="e.g. '2-8°C'")
    fragile = Column(Boolean, default=False)
    time_sensitive = Column(Boolean, default=False)
    special_instructions = Column(Text)
    
    # Customer Information
    customer_name = Column(String(255))
    customer_phone = Column(String(50))
    customer_email = Column(String(255))
    
    # Scheduling
    scheduled_pickup = Column(DateTime(timezone=True))
    scheduled_delivery = Column(DateTime(timezone=True))
    actual_pickup = Column(DateTime(timezone=True))
    actual_delivery = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Financial
    delivery_fee = Column(Float, default=0.0)
    insurance_value = Column(Float, default=0.0)
    
    # Tracking
    tracking_number = Column(String(100), unique=True)
    notes = Column(Text)
    custom_data = Column(JSON, default={})
    
    # Relationships
    mission = relationship("Mission", back_populates="orders")
    
    # Indexes
    __table_args__ = (
        Index('ix_order_status_priority', 'status', 'priority'),
        Index('ix_order_category_status', 'category', 'status'),
    )
    
    def to_dict(self):
        """Convert order to dictionary"""
        return {
            'id': self.id,
            'mission_id': self.mission_id,
            'order_number': self.order_number,
            'category': self.category.value if self.category else None,
            'priority': self.priority.value if self.priority else None,
            'status': self.status.value if self.status else None,
            'pickup_latitude': self.pickup_latitude,
            'pickup_longitude': self.pickup_longitude,
            'pickup_address': self.pickup_address,
            'pickup_contact_name': self.pickup_contact_name,
            'pickup_contact_phone': self.pickup_contact_phone,
            'delivery_latitude': self.delivery_latitude,
            'delivery_longitude': self.delivery_longitude,
            'delivery_address': self.delivery_address,
            'delivery_contact_name': self.delivery_contact_name,
            'delivery_contact_phone': self.delivery_contact_phone,
            'package_weight': self.package_weight,
            'package_dimensions': self.package_dimensions,
            'items': self.items,
            'item_count': self.item_count,
            'temperature_controlled': self.temperature_controlled,
            'temperature_range': self.temperature_range,
            'fragile': self.fragile,
            'time_sensitive': self.time_sensitive,
            'special_instructions': self.special_instructions,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'scheduled_pickup': self.scheduled_pickup.isoformat() if self.scheduled_pickup else None,
            'scheduled_delivery': self.scheduled_delivery.isoformat() if self.scheduled_delivery else None,
            'actual_pickup': self.actual_pickup.isoformat() if self.actual_pickup else None,
            'actual_delivery': self.actual_delivery.isoformat() if self.actual_delivery else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'delivery_fee': self.delivery_fee,
            'insurance_value': self.insurance_value,
            'tracking_number': self.tracking_number,
            'notes': self.notes,
            'custom_data': self.custom_data
        }
    
    def __repr__(self):
        return f"<Order(id={self.id}, order_number='{self.order_number}', status='{self.status.value}')>"
