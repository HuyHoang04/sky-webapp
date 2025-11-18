from flask import Blueprint, render_template, jsonify, request
from database import get_db
from model.mission_model import MissionStatus, OrderStatus
from services.mission_service import MissionService, OrderService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

mission_blueprint = Blueprint('mission', __name__)
mission_service = MissionService()
order_service = OrderService()

# ============================================
# WEB ROUTES
# ============================================

@mission_blueprint.route('/mission')
def mission_page():
    """Render mission management page"""
    return render_template('mission.html')

@mission_blueprint.route('/api/missions', methods=['GET', 'POST'])
def handle_missions():
    """Get all missions or create new mission"""
    if request.method == 'POST':
        try:
            data = request.json
            
            with get_db() as db:
                mission = mission_service.create_mission(db, data)
                
                return jsonify({
                    'status': 'success',
                    'message': 'Mission created successfully',
                    'mission': mission.to_dict()
                }), 201
                
        except Exception as e:
            logger.error(f"Error creating mission: {e}")
            return jsonify({
                'status': 'error', 
                'message': str(e)
            }), 400
    
    else:  # GET
        try:
            device_id = request.args.get('device_id')
            status = request.args.get('status')
            
            with get_db() as db:
                if status:
                    status = MissionStatus[status.upper()]
                
                missions = mission_service.get_all_missions(
                    db, 
                    device_id=device_id,
                    status=status
                )
                return jsonify([mission.to_dict() for mission in missions])
                
        except Exception as e:
            logger.error(f"Error fetching missions: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@mission_blueprint.route('/api/missions/<int:mission_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_mission(mission_id):
    """Get, update or delete a specific mission"""
    try:
        with get_db() as db:
            mission = mission_service.get_mission(db, mission_id)
            
            if not mission:
                return jsonify({
                    'status': 'error', 
                    'message': 'Mission not found'
                }), 404
            
            if request.method == 'GET':
                return jsonify(mission.to_dict())
            
            elif request.method == 'PUT':
                data = request.json
                mission = mission_service.update_mission(db, mission_id, data)
                
                return jsonify({
                    'status': 'success',
                    'message': 'Mission updated successfully',
                    'mission': mission.to_dict()
                })
            
            elif request.method == 'DELETE':
                success = mission_service.delete_mission(db, mission_id)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': 'Mission deleted successfully'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to delete mission'
                    }), 500
    
    except Exception as e:
        logger.error(f"Error handling mission {mission_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@mission_blueprint.route('/api/missions/<int:mission_id>/start', methods=['POST'])
def start_mission(mission_id):
    """Start a mission"""
    try:
        with get_db() as db:
            mission = mission_service.start_mission(db, mission_id)
            
            return jsonify({
                'status': 'success',
                'message': 'Mission started',
                'mission': mission.to_dict()
            })
            
    except Exception as e:
        logger.error(f"Error starting mission: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400

@mission_blueprint.route('/api/missions/<int:mission_id>/complete', methods=['POST'])
def complete_mission(mission_id):
    """Complete a mission"""
    try:
        with get_db() as db:
            mission = mission_service.complete_mission(db, mission_id)
            
            return jsonify({
                'status': 'success',
                'message': 'Mission completed',
                'mission': mission.to_dict()
            })
            
    except Exception as e:
        logger.error(f"Error completing mission: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400

@mission_blueprint.route('/api/missions/<int:mission_id>/optimize-route', methods=['POST'])
def optimize_mission_route(mission_id):
    """Optimize route for a mission with orders"""
    try:
        data = request.json or {}
        start_point = data.get('start_point')
        
        with get_db() as db:
            mission = mission_service.optimize_mission_route(
                db, 
                mission_id,
                start_point
            )
            
            return jsonify({
                'status': 'success',
                'message': 'Route optimized successfully',
                'mission': mission.to_dict()
            })
            
    except Exception as e:
        logger.error(f"Error optimizing route: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400

# ============================================
# ORDER API ENDPOINTS
# ============================================

@mission_blueprint.route('/api/orders', methods=['GET', 'POST'])
def handle_orders():
    """Get all orders or create new order"""
    if request.method == 'POST':
        try:
            data = request.json
            
            with get_db() as db:
                order = order_service.create_order(db, data)
                
                return jsonify({
                    'status': 'success',
                    'message': 'Order created successfully',
                    'order': order.to_dict()
                }), 201
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400
    
    else:  # GET
        try:
            mission_id = request.args.get('mission_id')
            
            with get_db() as db:
                if mission_id:
                    orders = order_service.get_orders_by_mission(db, int(mission_id))
                else:
                    # Get all orders (implement in service if needed)
                    orders = []
                
                return jsonify([order.to_dict() for order in orders])
                
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

@mission_blueprint.route('/api/orders/<int:order_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_order(order_id):
    """Get, update or delete a specific order"""
    try:
        with get_db() as db:
            order = order_service.get_order(db, order_id)
            
            if not order:
                return jsonify({
                    'status': 'error',
                    'message': 'Order not found'
                }), 404
            
            if request.method == 'GET':
                return jsonify(order.to_dict())
            
            elif request.method == 'PUT':
                data = request.json
                
                # Update order status if provided
                if 'status' in data:
                    new_status = OrderStatus[data['status'].upper()]
                    timestamp_field = data.get('timestamp_field')
                    order = order_service.update_order_status(
                        db, order_id, new_status, timestamp_field
                    )
                
                return jsonify({
                    'status': 'success',
                    'message': 'Order updated successfully',
                    'order': order.to_dict()
                })
            
            elif request.method == 'DELETE':
                success = order_service.delete_order(db, order_id)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': 'Order deleted successfully'
                    })
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Failed to delete order'
                    }), 500
    
    except Exception as e:
        logger.error(f"Error handling order {order_id}: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ============================================
# LEGACY ENDPOINT (for compatibility)
# ============================================

@mission_blueprint.route('/api/mission-config', methods=['POST'])
def save_mission_config():
    """Legacy endpoint - configuration is now saved with mission"""
    config = request.json
    logger.info(f"Received mission config: {config}")
    return jsonify({
        'status': 'success', 
        'message': 'Configuration will be saved with mission'
    })

# ============================================
# NOTE: Mission management uses REST API only
# WebSocket/Socket.IO is only for GPS real-time tracking
# ============================================