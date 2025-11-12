from flask import Blueprint, render_template, jsonify, request
from socket_instance import socketio

mission_blueprint = Blueprint('mission', __name__)

@mission_blueprint.route('/mission')
def mission_page():
    return render_template('mission.html')

@mission_blueprint.route('/api/missions', methods=['GET', 'POST'])
def handle_missions():
    if request.method == 'POST':
        mission_data = request.json
        # TODO: Store mission data in database
        return jsonify({'status': 'success', 'message': 'Mission created successfully'})
    else:
        # TODO: Retrieve missions from database
        missions = []
        return jsonify(missions)

@mission_blueprint.route('/api/mission-config', methods=['POST'])
def save_mission_config():
    config = request.json
    # TODO: Store configuration in database
    return jsonify({'status': 'success', 'message': 'Configuration saved successfully'})

# Socket.IO events for real-time mission updates
@socketio.on('mission_update')
def handle_mission_update(data):
    socketio.emit('mission_status', data, broadcast=True)

@socketio.on('waypoint_reached')
def handle_waypoint_reached(data):
    socketio.emit('waypoint_update', data, broadcast=True)