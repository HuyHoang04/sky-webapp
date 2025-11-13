"""
Route optimization service using graph algorithms
Provides TSP (Traveling Salesman Problem) and delivery route optimization
"""
import networkx as nx
import numpy as np
from typing import List, Tuple, Dict, Optional
from math import radians, cos, sin, asin, sqrt, ceil
import logging

logger = logging.getLogger(__name__)

class RouteOptimizer:
    """
    Route optimization using various algorithms:
    - Nearest Neighbor for TSP
    - Greedy algorithm for delivery routes
    - Haversine distance for geographic calculations
    """
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on earth
        
        Args:
            lat1, lon1: Coordinates of first point (decimal degrees)
            lat2, lon2: Coordinates of second point (decimal degrees)
            
        Returns:
            Distance in meters
        """
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        # Radius of earth in meters
        r = 6371000
        
        return c * r
    
    @staticmethod
    def calculate_cost(distance: float, time: float, priority: float = 1.0) -> float:
        """
        Calculate route cost considering distance, time, and priority
        Lower cost is better
        
        Args:
            distance: Distance in meters
            time: Time in seconds
            priority: Priority weight (1.0=low, 2.0=medium, 3.0=high, 4.0=critical)
            
        Returns:
            Combined cost (lower is better)
        """
        # Normalize and weight factors
        distance_weight = 0.6
        time_weight = 0.3
        priority_weight = 0.1
        
        # Priority reduces cost (higher priority = lower cost)
        priority_factor = 1.0 / priority if priority > 0 else 1.0
        
        return (distance * distance_weight + 
                time * time_weight + 
                priority_factor * priority_weight * 1000)
    
    def optimize_waypoints_tsp(self, waypoints: List[Dict], start_index: int = 0) -> List[Dict]:
        """
        Optimize waypoint order using Nearest Neighbor TSP heuristic
        Good for simple point-to-point missions
        
        Args:
            waypoints: List of waypoint dicts with 'latitude' and 'longitude'
            start_index: Index of starting waypoint (default 0)
            
        Returns:
            Optimized list of waypoints with updated 'sequence' field
        """
        if len(waypoints) <= 2:
            for idx, wp in enumerate(waypoints):
                wp['sequence'] = idx + 1
            return waypoints
        
        try:
            n = len(waypoints)
            
            # Create distance matrix
            distances = np.zeros((n, n))
            for i in range(n):
                for j in range(n):
                    if i != j:
                        distances[i][j] = self.haversine_distance(
                            waypoints[i]['latitude'], waypoints[i]['longitude'],
                            waypoints[j]['latitude'], waypoints[j]['longitude']
                        )
            
            # Nearest neighbor algorithm
            unvisited = set(range(n))
            current = start_index
            route = [current]
            unvisited.remove(current)
            
            while unvisited:
                # Find nearest unvisited waypoint
                nearest = min(unvisited, key=lambda x: distances[current][x])
                route.append(nearest)
                unvisited.remove(nearest)
                current = nearest
            
            # Reorder waypoints and update sequences
            optimized = [waypoints[i] for i in route]
            for idx, wp in enumerate(optimized):
                wp['sequence'] = idx + 1
            
            # Calculate total distance
            total_distance = sum(
                distances[route[i]][route[i+1]] 
                for i in range(len(route)-1)
            )
            
            logger.info(f"TSP optimization: {n} waypoints, total distance: {total_distance/1000:.2f}km")
            return optimized
            
        except Exception as e:
            logger.error(f"Error in TSP optimization: {e}")
            # Return original waypoints if optimization fails
            for idx, wp in enumerate(waypoints):
                wp['sequence'] = idx + 1
            return waypoints
    
    def optimize_delivery_route(
        self, 
        orders: List[Dict], 
        start_point: Dict,
        consider_priority: bool = True
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Optimize delivery route considering pickup and delivery points
        Uses greedy algorithm with priority consideration
        
        Args:
            orders: List of order dicts with pickup/delivery locations and priority
            start_point: Starting location {'latitude': ..., 'longitude': ...}
            consider_priority: Whether to factor in order priority
            
        Returns:
            Tuple of (optimized_orders, waypoints_sequence)
        """
        if not orders:
            return [], []
        
        try:
            # Create graph
            G = nx.DiGraph()
            
            # Add start node
            G.add_node('start', 
                      lat=start_point['latitude'], 
                      lng=start_point['longitude'],
                      type='start')
            
            # Priority mapping
            priority_values = {
                'low': 1.0,
                'medium': 2.0,
                'high': 3.0,
                'critical': 4.0
            }
            
            # Add pickup and delivery nodes for each order
            for idx, order in enumerate(orders):
                pickup_id = f"pickup_{idx}"
                delivery_id = f"delivery_{idx}"
                
                priority = priority_values.get(order.get('priority', 'medium'), 2.0)
                
                G.add_node(pickup_id,
                          lat=order['pickup_latitude'],
                          lng=order['pickup_longitude'],
                          order_id=order.get('id'),
                          order_index=idx,
                          type='pickup',
                          priority=priority)
                
                G.add_node(delivery_id,
                          lat=order['delivery_latitude'],
                          lng=order['delivery_longitude'],
                          order_id=order.get('id'),
                          order_index=idx,
                          type='delivery',
                          priority=priority)
                
                # Mandatory edge: must pickup before delivery
                distance = self.haversine_distance(
                    order['pickup_latitude'], order['pickup_longitude'],
                    order['delivery_latitude'], order['delivery_longitude']
                )
                G.add_edge(pickup_id, delivery_id, weight=distance, mandatory=True)
            
            # Build route using greedy algorithm
            current = 'start'
            route = [current]
            visited_orders = set()
            
            while len(visited_orders) < len(orders):
                candidates = []
                
                # Find best next waypoint
                for idx in range(len(orders)):
                    if idx not in visited_orders:
                        pickup_id = f"pickup_{idx}"
                        
                        # Can only go to pickup if not yet visited
                        if pickup_id not in route:
                            node_data = G.nodes[pickup_id]
                            current_data = G.nodes[current]
                            
                            distance = self.haversine_distance(
                                current_data['lat'], current_data['lng'],
                                node_data['lat'], node_data['lng']
                            )
                            
                            flight_time = distance / 5.0  # Assume 5 m/s speed
                            priority = node_data['priority'] if consider_priority else 1.0
                            
                            cost = self.calculate_cost(distance, flight_time, priority)
                            candidates.append((pickup_id, cost, idx))
                
                if candidates:
                    # Choose candidate with lowest cost
                    next_node, _, order_idx = min(candidates, key=lambda x: x[1])
                    route.append(next_node)
                    
                    # Immediately add corresponding delivery
                    delivery_id = f"delivery_{order_idx}"
                    route.append(delivery_id)
                    visited_orders.add(order_idx)
                    current = delivery_id
                else:
                    break
            
            # Convert route to waypoints
            waypoints = []
            sequence = 1
            
            for node in route:
                if node == 'start':
                    continue
                
                node_data = G.nodes[node]
                order_idx = node_data.get('order_index')
                
                waypoint = {
                    'sequence': sequence,
                    'latitude': node_data['lat'],
                    'longitude': node_data['lng'],
                    'waypoint_type': node_data['type'],
                    'action': 'pickup' if node_data['type'] == 'pickup' else 'delivery',
                    'action_params': {
                        'order_id': node_data.get('order_id'),
                        'order_index': order_idx
                    },
                    'name': f"{node_data['type'].title()} - Order #{orders[order_idx].get('order_number', order_idx+1)}" if order_idx is not None else None
                }
                waypoints.append(waypoint)
                sequence += 1
            
            logger.info(f"Delivery route optimized: {len(orders)} orders, {len(waypoints)} waypoints")
            return orders, waypoints
            
        except Exception as e:
            logger.error(f"Error optimizing delivery route: {e}")
            
            # Fallback: simple sequential route
            waypoints = []
            for idx, order in enumerate(orders):
                waypoints.extend([
                    {
                        'sequence': idx * 2 + 1,
                        'latitude': order['pickup_latitude'],
                        'longitude': order['pickup_longitude'],
                        'waypoint_type': 'pickup',
                        'action': 'pickup',
                        'action_params': {'order_id': order.get('id')},
                        'name': f"Pickup - Order #{order.get('order_number', idx+1)}"
                    },
                    {
                        'sequence': idx * 2 + 2,
                        'latitude': order['delivery_latitude'],
                        'longitude': order['delivery_longitude'],
                        'waypoint_type': 'delivery',
                        'action': 'delivery',
                        'action_params': {'order_id': order.get('id')},
                        'name': f"Delivery - Order #{order.get('order_number', idx+1)}"
                    }
                ])
            return orders, waypoints
    
    def calculate_route_statistics(
        self, 
        waypoints: List[Dict], 
        flight_speed: float = 5.0,
        photo_interval: float = 2.0
    ) -> Dict:
        """
        Calculate comprehensive statistics for a route
        
        Args:
            waypoints: List of waypoints with lat/lng
            flight_speed: Average flight speed in m/s
            photo_interval: Photo capture interval in seconds
            
        Returns:
            Dictionary with route statistics
        """
        if not waypoints or len(waypoints) < 2:
            return {
                'total_distance': 0.0,
                'estimated_duration': 0,
                'waypoint_count': len(waypoints),
                'photos_estimated': 0,
                'battery_required': 0.0
            }
        
        total_distance = 0.0
        total_hover_time = 0.0
        
        # Calculate distances between consecutive waypoints
        for i in range(len(waypoints) - 1):
            distance = self.haversine_distance(
                waypoints[i]['latitude'], waypoints[i]['longitude'],
                waypoints[i + 1]['latitude'], waypoints[i + 1]['longitude']
            )
            total_distance += distance
            
            # Add hover time if specified
            hover_time = waypoints[i].get('hover_time', 0.0)
            total_hover_time += hover_time
        
        # Calculate flight time
        flight_time = total_distance / flight_speed  # seconds
        total_time = flight_time + total_hover_time
        
        # Estimate photos (one photo every photo_interval seconds)
        photos_estimated = ceil(flight_time / photo_interval) if photo_interval > 0 else 0
        
        # Estimate battery usage (rough estimate: 1% per minute of flight)
        battery_required = min((total_time / 60) * 1.0, 100.0)
        
        return {
            'total_distance': round(total_distance / 1000, 2),  # Convert to km
            'estimated_duration': int(total_time),  # seconds
            'flight_time': int(flight_time),
            'hover_time': int(total_hover_time),
            'waypoint_count': len(waypoints),
            'photos_estimated': photos_estimated,
            'battery_required': round(battery_required, 1)
        }
    
    def add_return_to_home(self, waypoints: List[Dict], home_point: Dict) -> List[Dict]:
        """
        Add return to home waypoint at the end of mission
        
        Args:
            waypoints: List of mission waypoints
            home_point: Home location {'latitude': ..., 'longitude': ...}
            
        Returns:
            Waypoints with RTH added
        """
        if not waypoints:
            return waypoints
        
        # Check if last waypoint is already home
        last_wp = waypoints[-1]
        if (abs(last_wp['latitude'] - home_point['latitude']) < 0.0001 and
            abs(last_wp['longitude'] - home_point['longitude']) < 0.0001):
            return waypoints
        
        # Add RTH waypoint
        rth_waypoint = {
            'sequence': len(waypoints) + 1,
            'latitude': home_point['latitude'],
            'longitude': home_point['longitude'],
            'altitude': home_point.get('altitude', 70.0),
            'waypoint_type': 'home',
            'action': 'land',
            'name': 'Return to Home'
        }
        
        waypoints.append(rth_waypoint)
        logger.info("Added return to home waypoint")
        
        return waypoints
