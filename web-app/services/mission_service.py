"""
Mission service - Business logic layer for mission operations
Handles CRUD operations and complex mission workflows
"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging

from model.mission_model import (
    Mission, Waypoint, Route, Order,
    MissionStatus, MissionType, OrderStatus, OrderPriority, OrderCategory, WaypointType
)
from services.route_optimizer import RouteOptimizer

logger = logging.getLogger(__name__)

class MissionService:
    """
    Service class for mission management
    """
    
    def __init__(self):
        self.route_optimizer = RouteOptimizer()
    
    def create_mission(self, db: Session, mission_data: Dict) -> Mission:
        """
        Create a new mission with waypoints
        
        Args:
            db: Database session
            mission_data: Dictionary containing mission configuration
            
        Returns:
            Created Mission object
        """
        try:
            # Extract configuration
            config = mission_data.get('configuration', {})
            
            # Create mission
            mission = Mission(
                name=mission_data['name'],
                mission_type=MissionType[mission_data.get('mission_type', mission_data.get('type', 'survey')).upper()],
                device_id=mission_data.get('device_id', 'drone1'),
                device_name=mission_data.get('device_name', 'Drone 1'),
                flight_height=mission_data.get('flight_altitude', config.get('flightHeight', 50.0)),
                flight_speed=mission_data.get('flight_speed', config.get('flightSpeed', 5.0)),
                return_altitude=mission_data.get('return_altitude', config.get('returnAltitude', 70.0)),
                photo_interval=mission_data.get('photo_interval', config.get('photoInterval', 2.0)),
                overlap=config.get('overlap', 75.0),
                camera_angle=config.get('cameraAngle', 90.0),
                min_battery=mission_data.get('min_battery_rth', config.get('minBattery', 30.0)),
                max_distance=mission_data.get('max_flight_distance', config.get('maxDistance', 2000.0)),
                obstacle_avoidance=mission_data.get('enable_obstacle_avoidance', config.get('obstacleAvoidance', True)),
                geofencing=mission_data.get('enable_geofencing', config.get('geofencing', True)),
                emergency_rth=config.get('emergencyRTH', True),
                scheduled_start=datetime.fromisoformat(mission_data['startTime']) if mission_data.get('startTime') else None,
                description=mission_data.get('description', ''),
                notes=mission_data.get('notes', ''),
                custom_data=mission_data.get('custom_data', mission_data.get('metadata', {}))
            )
            
            db.add(mission)
            db.flush()  # Get mission ID
            
            # Process waypoints
            waypoints_data = mission_data.get('waypoints', [])
            
            # Optimize waypoints if requested
            if mission_data.get('optimize', True) and len(waypoints_data) > 2:
                waypoints_data = self.route_optimizer.optimize_waypoints_tsp(waypoints_data)
            
            # Create waypoints
            for wp_data in waypoints_data:
                waypoint = Waypoint(
                    mission_id=mission.id,
                    sequence=wp_data.get('sequence', 0),
                    name=wp_data.get('name'),
                    waypoint_type=WaypointType[wp_data.get('type', 'point').upper()],
                    latitude=wp_data.get('lat', wp_data.get('latitude')),
                    longitude=wp_data.get('lng', wp_data.get('longitude')),
                    altitude=wp_data.get('altitude', mission.flight_height),
                    action=wp_data.get('action'),
                    action_params=wp_data.get('action_params', {}),
                    hover_time=wp_data.get('hover_time', 0.0),
                    notes=wp_data.get('notes', ''),
                    custom_data=wp_data.get('custom_data', wp_data.get('metadata', {}))
                )
                db.add(waypoint)
            
            # Calculate mission statistics
            if waypoints_data:
                stats = self.route_optimizer.calculate_route_statistics(
                    waypoints_data,
                    mission.flight_speed,
                    mission.photo_interval
                )
                mission.total_distance = stats['total_distance']
                mission.estimated_duration = stats['estimated_duration']
                mission.battery_required = stats['battery_required']
                mission.photos_estimated = stats['photos_estimated']
                mission.waypoint_count = stats['waypoint_count']
            
            db.commit()
            db.refresh(mission)
            
            logger.info(f"Created mission: {mission.name} (ID: {mission.id})")
            return mission
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating mission: {e}")
            raise
    
    def get_mission(self, db: Session, mission_id: int) -> Optional[Mission]:
        """Get mission by ID"""
        return db.query(Mission).filter(Mission.id == mission_id).first()
    
    def get_all_missions(
        self, 
        db: Session, 
        device_id: Optional[str] = None,
        status: Optional[MissionStatus] = None,
        limit: int = 100
    ) -> List[Mission]:
        """
        Get all missions with optional filtering
        
        Args:
            db: Database session
            device_id: Filter by device ID
            status: Filter by mission status
            limit: Maximum number of results
            
        Returns:
            List of Mission objects
        """
        query = db.query(Mission)
        
        if device_id:
            query = query.filter(Mission.device_id == device_id)
        
        if status:
            query = query.filter(Mission.status == status)
        
        return query.order_by(Mission.created_at.desc()).limit(limit).all()
    
    def update_mission(self, db: Session, mission_id: int, update_data: Dict) -> Mission:
        """
        Update mission fields
        
        Args:
            db: Database session
            mission_id: Mission ID to update
            update_data: Dictionary of fields to update
            
        Returns:
            Updated Mission object
        """
        try:
            mission = self.get_mission(db, mission_id)
            if not mission:
                raise ValueError(f"Mission {mission_id} not found")
            
            # Update allowed fields
            for key, value in update_data.items():
                if hasattr(mission, key) and key not in ['id', 'created_at']:
                    # Handle enum conversions
                    if key == 'status' and isinstance(value, str):
                        value = MissionStatus[value.upper()]
                    elif key == 'mission_type' and isinstance(value, str):
                        value = MissionType[value.upper()]
                    
                    setattr(mission, key, value)
            
            db.commit()
            db.refresh(mission)
            
            logger.info(f"Updated mission: {mission.id}")
            return mission
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating mission: {e}")
            raise
    
    def delete_mission(self, db: Session, mission_id: int) -> bool:
        """
        Delete mission and all related data (cascades)
        
        Args:
            db: Database session
            mission_id: Mission ID to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            mission = self.get_mission(db, mission_id)
            if not mission:
                return False
            
            db.delete(mission)
            db.commit()
            
            logger.info(f"Deleted mission: {mission_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting mission: {e}")
            raise
    
    def start_mission(self, db: Session, mission_id: int) -> Mission:
        """Start a mission (update status and set actual_start)"""
        mission = self.get_mission(db, mission_id)
        if not mission:
            raise ValueError(f"Mission {mission_id} not found")
        
        mission.status = MissionStatus.IN_PROGRESS
        mission.actual_start = datetime.utcnow()
        
        db.commit()
        db.refresh(mission)
        
        logger.info(f"Started mission: {mission.id}")
        return mission
    
    def complete_mission(self, db: Session, mission_id: int) -> Mission:
        """Complete a mission (update status and set actual_end)"""
        mission = self.get_mission(db, mission_id)
        if not mission:
            raise ValueError(f"Mission {mission_id} not found")
        
        mission.status = MissionStatus.COMPLETED
        mission.actual_end = datetime.utcnow()
        
        db.commit()
        db.refresh(mission)
        
        logger.info(f"Completed mission: {mission.id}")
        return mission
    
    def optimize_mission_route(
        self, 
        db: Session, 
        mission_id: int, 
        start_point: Optional[Dict] = None
    ) -> Mission:
        """
        Optimize route for a mission with orders
        Recalculates waypoints based on order locations
        
        Args:
            db: Database session
            mission_id: Mission ID
            start_point: Starting location (default: first waypoint)
            
        Returns:
            Updated Mission object
        """
        try:
            mission = self.get_mission(db, mission_id)
            if not mission:
                raise ValueError(f"Mission {mission_id} not found")
            
            # Get mission orders
            orders = db.query(Order).filter(Order.mission_id == mission_id).all()
            
            if not orders:
                raise ValueError("No orders found for this mission")
            
            # Determine start point
            if not start_point:
                # Use first waypoint or default location
                first_wp = db.query(Waypoint).filter(
                    Waypoint.mission_id == mission_id
                ).order_by(Waypoint.sequence).first()
                
                if first_wp:
                    start_point = {
                        'latitude': first_wp.latitude,
                        'longitude': first_wp.longitude
                    }
                else:
                    # Default to Hanoi coordinates
                    start_point = {'latitude': 21.0285, 'longitude': 105.8542}
            
            # Convert orders to dict
            orders_data = [order.to_dict() for order in orders]
            
            # Optimize route
            _, waypoints = self.route_optimizer.optimize_delivery_route(
                orders_data, 
                start_point,
                consider_priority=True
            )
            
            # Delete existing waypoints
            db.query(Waypoint).filter(Waypoint.mission_id == mission_id).delete()
            
            # Create new optimized waypoints
            for wp_data in waypoints:
                waypoint = Waypoint(
                    mission_id=mission_id,
                    sequence=wp_data['sequence'],
                    latitude=wp_data['latitude'],
                    longitude=wp_data['longitude'],
                    altitude=mission.flight_height,
                    waypoint_type=WaypointType[wp_data['waypoint_type'].upper()],
                    action=wp_data['action'],
                    action_params=wp_data.get('action_params', {}),
                    name=wp_data.get('name')
                )
                db.add(waypoint)
            
            # Update mission statistics
            stats = self.route_optimizer.calculate_route_statistics(
                waypoints, 
                mission.flight_speed,
                mission.photo_interval
            )
            mission.total_distance = stats['total_distance']
            mission.estimated_duration = stats['estimated_duration']
            mission.battery_required = stats['battery_required']
            mission.waypoint_count = stats['waypoint_count']
            
            db.commit()
            db.refresh(mission)
            
            logger.info(f"Optimized route for mission {mission_id}: {len(waypoints)} waypoints")
            return mission
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error optimizing mission route: {e}")
            raise

class OrderService:
    """
    Service class for order management
    """
    
    def create_order(self, db: Session, order_data: Dict) -> Order:
        """
        Create a new delivery order
        
        Args:
            db: Database session
            order_data: Dictionary containing order details
            
        Returns:
            Created Order object
        """
        try:
            order = Order(
                mission_id=order_data.get('mission_id'),
                order_number=order_data['order_number'],
                category=OrderCategory[order_data['category'].upper()],
                priority=OrderPriority[order_data.get('priority', 'MEDIUM').upper()],
                pickup_latitude=order_data['pickup_location']['lat'],
                pickup_longitude=order_data['pickup_location']['lng'],
                pickup_address=order_data.get('pickup_address'),
                pickup_contact_name=order_data.get('pickup_contact_name'),
                pickup_contact_phone=order_data.get('pickup_contact_phone'),
                delivery_latitude=order_data['delivery_location']['lat'],
                delivery_longitude=order_data['delivery_location']['lng'],
                delivery_address=order_data.get('delivery_address'),
                delivery_contact_name=order_data.get('delivery_contact_name'),
                delivery_contact_phone=order_data.get('delivery_contact_phone'),
                package_weight=order_data.get('package_weight'),
                package_dimensions=order_data.get('package_dimensions'),
                items=order_data.get('items', []),
                item_count=len(order_data.get('items', [])),
                temperature_controlled=order_data.get('temperature_controlled', False),
                temperature_range=order_data.get('temperature_range'),
                fragile=order_data.get('fragile', False),
                time_sensitive=order_data.get('time_sensitive', False),
                special_instructions=order_data.get('special_instructions'),
                customer_name=order_data.get('customer_name'),
                customer_phone=order_data.get('customer_phone'),
                customer_email=order_data.get('customer_email'),
                scheduled_pickup=datetime.fromisoformat(order_data['scheduled_pickup']) if order_data.get('scheduled_pickup') else None,
                scheduled_delivery=datetime.fromisoformat(order_data['scheduled_delivery']) if order_data.get('scheduled_delivery') else None,
                delivery_fee=order_data.get('delivery_fee', 0.0),
                insurance_value=order_data.get('insurance_value', 0.0),
                notes=order_data.get('notes'),
                custom_data=order_data.get('custom_data', order_data.get('metadata', {}))
            )
            
            db.add(order)
            db.commit()
            db.refresh(order)
            
            logger.info(f"Created order: {order.order_number}")
            return order
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating order: {e}")
            raise
    
    def get_order(self, db: Session, order_id: int) -> Optional[Order]:
        """Get order by ID"""
        return db.query(Order).filter(Order.id == order_id).first()
    
    def get_orders_by_mission(self, db: Session, mission_id: int) -> List[Order]:
        """Get all orders for a specific mission"""
        return db.query(Order).filter(Order.mission_id == mission_id).all()
    
    def update_order_status(
        self, 
        db: Session, 
        order_id: int, 
        new_status: OrderStatus,
        timestamp_field: Optional[str] = None
    ) -> Order:
        """
        Update order status and optionally set timestamp
        
        Args:
            db: Database session
            order_id: Order ID
            new_status: New OrderStatus enum value
            timestamp_field: Field name to update (e.g., 'actual_pickup')
        """
        order = self.get_order(db, order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        order.status = new_status
        
        if timestamp_field and hasattr(order, timestamp_field):
            setattr(order, timestamp_field, datetime.utcnow())
        
        db.commit()
        db.refresh(order)
        
        logger.info(f"Updated order {order_id} status to {new_status.value}")
        return order
    
    def delete_order(self, db: Session, order_id: int) -> bool:
        """
        Delete an order
        
        Args:
            db: Database session
            order_id: Order ID
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            order = self.get_order(db, order_id)
            if not order:
                logger.warning(f"Order {order_id} not found for deletion")
                return False
            
            db.delete(order)
            db.commit()
            
            logger.info(f"Deleted order {order_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting order {order_id}: {e}")
            raise

