/**
 * Mission Management - Integration with ORM Backend
 */

// Global variables
let missionMap;
let drawnItems;
let drawControl;
let currentMission = null;
let allMissions = [];
let activeMissionMarkers = [];
let tempOrders = []; // Temporary orders for mission creation

// Initialize Mission Management
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadMissions();
    setupEventListeners();
    connectWebSocket();
    setupModalOrdersToggle();
});

// Initialize Leaflet Map
function initializeMap() {
    missionMap = L.map('mission-map').setView([21.0285, 105.8542], 13);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(missionMap);

    // Initialize drawing layer
    drawnItems = new L.FeatureGroup();
    missionMap.addLayer(drawnItems);

    // Setup drawing controls
    drawControl = new L.Control.Draw({
        draw: {
            polygon: {
                allowIntersection: false,
                showArea: true,
                shapeOptions: {
                    color: '#52c41a'
                }
            },
            polyline: {
                shapeOptions: {
                    color: '#1890ff'
                }
            },
            circle: false,
            rectangle: false,
            circlemarker: false,
            marker: {
                icon: L.icon({
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                })
            }
        },
        edit: {
            featureGroup: drawnItems,
            remove: true
        }
    });
    missionMap.addControl(drawControl);

    // Handle drawing events
    missionMap.on(L.Draw.Event.CREATED, handleDrawCreated);
    missionMap.on(L.Draw.Event.EDITED, handleDrawEdited);
    missionMap.on(L.Draw.Event.DELETED, handleDrawDeleted);
}

// Handle draw created
function handleDrawCreated(event) {
    const layer = event.layer;
    drawnItems.addLayer(layer);
    updateMissionStats();
    updateWaypointList();
}

// Handle draw edited
function handleDrawEdited(event) {
    updateMissionStats();
    updateWaypointList();
}

// Handle draw deleted
function handleDrawDeleted(event) {
    updateMissionStats();
    updateWaypointList();
}

// Load all missions from backend
async function loadMissions() {
    try {
        const response = await fetch('/api/missions');
        if (!response.ok) throw new Error('Failed to load missions');
        
        allMissions = await response.json();
        displayMissions(allMissions);
        
        // Load active mission if exists
        const activeMission = allMissions.find(m => m.status === 'in_progress');
        if (activeMission) {
            displayActiveMission(activeMission);
        }
    } catch (error) {
        console.error('Error loading missions:', error);
        showToast('Error loading missions', 'error');
    }
}

// Display missions in sidebar
function displayMissions(missions) {
    const missionsListContainer = document.getElementById('missionsList');
    if (!missionsListContainer) return;
    
    if (missions.length === 0) {
        missionsListContainer.innerHTML = '<p class="text-muted text-center py-3 mb-0">No missions yet</p>';
        return;
    }
    
    // Sort by created date (newest first)
    missions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    let html = '';
    missions.forEach(mission => {
        const statusBadge = getStatusBadge(mission.status);
        const statusClass = getStatusClass(mission.status);
        const createdDate = new Date(mission.created_at).toLocaleString();
        
        html += `
            <div class="mission-card ${statusClass} p-3 mb-3">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <h6 class="mb-1">${mission.name}</h6>
                        <small class="text-muted d-block">${mission.device_id || 'No device'}</small>
                        <small class="text-muted">${createdDate}</small>
                    </div>
                    ${statusBadge}
                </div>
                <div class="small text-muted mb-2">
                    <i class="fas fa-route me-1"></i> ${mission.waypoint_count || 0} waypoints
                    <i class="fas fa-ruler ms-2 me-1"></i> ${(mission.total_distance || 0).toFixed(2)} km
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-outline-success" onclick="viewMissionRoute(${mission.id})">
                        <i class="fas fa-route"></i> Route
                    </button>
                    <button class="btn btn-sm btn-outline-info" onclick="showMissionDetailOnly(${mission.id})">
                        <i class="fas fa-eye"></i> Detail
                    </button>
                    ${mission.status === 'draft' || mission.status === 'planned' ? `
                        <button class="btn btn-sm btn-primary" onclick="startMission(${mission.id})">
                            <i class="fas fa-play"></i>
                        </button>
                        <button class="btn btn-sm btn-info" onclick="editMission(${mission.id})">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteMission(${mission.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : ''}
                    ${mission.status === 'in_progress' ? `
                        <button class="btn btn-sm btn-warning" onclick="pauseMission(${mission.id})">
                            <i class="fas fa-pause"></i> Pause
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="stopMission(${mission.id})">
                            <i class="fas fa-stop"></i> Stop
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    missionsListContainer.innerHTML = html;
}

// Get status badge HTML
function getStatusBadge(status) {
    const badges = {
        'draft': '<span class="badge bg-secondary">Draft</span>',
        'planned': '<span class="badge bg-warning">Planned</span>',
        'ready': '<span class="badge bg-info">Ready</span>',
        'in_progress': '<span class="badge bg-success">In Progress</span>',
        'paused': '<span class="badge bg-warning">Paused</span>',
        'completed': '<span class="badge bg-success">Completed</span>',
        'cancelled': '<span class="badge bg-danger">Cancelled</span>',
        'failed': '<span class="badge bg-danger">Failed</span>'
    };
    return badges[status] || '<span class="badge bg-secondary">Unknown</span>';
}

// Get status CSS class
function getStatusClass(status) {
    const classes = {
        'draft': 'mission-planned',
        'planned': 'mission-planned',
        'ready': 'mission-planned',
        'in_progress': 'mission-active',
        'paused': 'mission-planned',
        'completed': 'mission-completed',
        'cancelled': 'mission-completed',
        'failed': 'mission-completed'
    };
    return classes[status] || '';
}

// Display active mission
function displayActiveMission(mission) {
    const container = document.querySelector('.mission-card.mission-active');
    if (!container) return;
    
    const progress = mission.waypoints_completed / mission.total_waypoints * 100 || 0;
    const startedAgo = getTimeAgo(mission.started_at);
    
    container.innerHTML = `
        <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
                <h6 class="mb-1">${mission.name}</h6>
                <small class="text-muted">Started ${startedAgo}</small>
            </div>
            <span class="badge bg-success">In Progress</span>
        </div>
        <div class="progress" style="height: 4px;">
            <div class="progress-bar bg-success" style="width: ${progress}%"></div>
        </div>
        <div class="mt-2 small text-muted">
            ${mission.waypoints_completed || 0} of ${mission.total_waypoints || 0} waypoints completed
        </div>
        <div class="mt-3">
            <button class="btn btn-sm btn-danger me-2" onclick="stopMission(${mission.id})">
                <i class="fas fa-stop-circle me-1"></i>Stop
            </button>
            <button class="btn btn-sm btn-warning" onclick="pauseMission(${mission.id})">
                <i class="fas fa-pause-circle me-1"></i>Pause
            </button>
        </div>
    `;
    
    currentMission = mission;
    
    // Display mission waypoints on map
    displayMissionWaypoints(mission);
}

// Display mission waypoints on map
function displayMissionWaypoints(mission) {
    // Clear existing markers
    activeMissionMarkers.forEach(marker => missionMap.removeLayer(marker));
    activeMissionMarkers = [];
    
    if (!mission.waypoints || mission.waypoints.length === 0) return;
    
    // Add waypoint markers
    mission.waypoints.forEach((waypoint, index) => {
        const marker = L.marker([waypoint.latitude, waypoint.longitude], {
            icon: L.divIcon({
                className: 'custom-div-icon',
                html: `<div style="background-color: #1890ff; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid white;">${index + 1}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            })
        });
        
        marker.bindPopup(`
            <b>Waypoint ${index + 1}</b><br>
            Lat: ${waypoint.latitude.toFixed(6)}<br>
            Lng: ${waypoint.longitude.toFixed(6)}<br>
            Alt: ${waypoint.altitude}m<br>
            Action: ${waypoint.action || 'hover'}
        `);
        
        marker.addTo(missionMap);
        activeMissionMarkers.push(marker);
    });
    
    // Draw route line
    if (mission.waypoints.length > 1) {
        const routeCoords = mission.waypoints.map(wp => [wp.latitude, wp.longitude]);
        const routeLine = L.polyline(routeCoords, {
            color: '#1890ff',
            weight: 3,
            opacity: 0.7,
            dashArray: '5, 10'
        });
        routeLine.addTo(missionMap);
        activeMissionMarkers.push(routeLine);
    }
    
    // Fit map to show all waypoints
    if (mission.waypoints.length > 0) {
        const bounds = L.latLngBounds(mission.waypoints.map(wp => [wp.latitude, wp.longitude]));
        missionMap.fitBounds(bounds, { padding: [50, 50] });
    }
}

// Create new mission
async function createNewMission() {
    // Check if user wants to add orders
    if (document.getElementById('modalAddOrders').checked && tempOrders.length > 0) {
        return await createMissionWithOrders();
    }
    
    const missionData = {
        name: document.getElementById('missionName').value.trim(),
        mission_type: document.getElementById('newMissionType').value,
        description: document.getElementById('missionDescription').value.trim(),
        device_id: document.getElementById('modalDeviceId').value.trim(),
        device_name: document.getElementById('modalDeviceName').value.trim(),
        waypoints: [],
        // Flight Parameters
        flight_height: parseFloat(document.getElementById('modalFlightHeight').value),
        flight_speed: parseFloat(document.getElementById('modalFlightSpeed').value),
        return_altitude: parseFloat(document.getElementById('modalReturnAltitude').value),
        photo_interval: parseFloat(document.getElementById('modalPhotoInterval').value),
        overlap: parseFloat(document.getElementById('modalOverlap').value),
        camera_angle: parseFloat(document.getElementById('modalCameraAngle').value),
        // Safety Settings
        min_battery: parseFloat(document.getElementById('modalMinBattery').value),
        max_distance: parseFloat(document.getElementById('modalMaxDistance').value),
        obstacle_avoidance: document.getElementById('modalObstacleAvoidance').checked,
        geofencing: document.getElementById('modalGeofencing').checked,
        emergency_rth: document.getElementById('modalEmergencyRth').checked
    };
    
    // Validate required fields
    if (!missionData.name) {
        showToast('Please enter mission name', 'error');
        return;
    }
    
    if (!missionData.device_id) {
        showToast('Please enter device ID', 'error');
        return;
    }
    
    // Convert drawn items to waypoints
    let sequence = 1;
    drawnItems.eachLayer(function(layer) {
        if (layer instanceof L.Marker) {
            const latlng = layer.getLatLng();
            missionData.waypoints.push({
                latitude: latlng.lat,
                longitude: latlng.lng,
                altitude: missionData.flight_altitude,
                sequence: sequence++,
                action: 'hover',
                waypoint_type: 'waypoint'
            });
        } else if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
            const latlngs = layer.getLatLngs();
            latlngs.forEach(latlng => {
                missionData.waypoints.push({
                    latitude: latlng.lat,
                    longitude: latlng.lng,
                    altitude: missionData.flight_altitude,
                    sequence: sequence++,
                    action: 'flyto',
                    waypoint_type: 'waypoint'
                });
            });
        }
    });
    
    if (missionData.waypoints.length === 0) {
        showToast('Please add at least one waypoint', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/missions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(missionData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create mission');
        }
        
        const newMission = await response.json();
        showToast('Mission created successfully', 'success');
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('newMissionModal'));
        modal.hide();
        
        // Reload missions
        await loadMissions();
        
        // Clear form
        document.getElementById('missionName').value = '';
        document.getElementById('missionDescription').value = '';
        
    } catch (error) {
        console.error('Error creating mission:', error);
        showToast(error.message, 'error');
    }
}

// Edit mission
async function editMission(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}`);
        if (!response.ok) throw new Error('Failed to load mission');
        
        const mission = await response.json();
        
        // Fill form with mission data
        document.getElementById('editMissionId').value = mission.id;
        document.getElementById('editMissionName').value = mission.name || '';
        document.getElementById('editMissionType').value = mission.mission_type || 'survey';
        document.getElementById('editDeviceId').value = mission.device_id || '';
        document.getElementById('editDeviceName').value = mission.device_name || '';
        document.getElementById('editMissionStatus').value = mission.status || 'draft';
        document.getElementById('editMissionDescription').value = mission.description || '';
        
        // Flight parameters
        document.getElementById('editFlightHeight').value = mission.flight_height || 50;
        document.getElementById('editFlightSpeed').value = mission.flight_speed || 5;
        document.getElementById('editReturnAltitude').value = mission.return_altitude || 70;
        document.getElementById('editPhotoInterval').value = mission.photo_interval || 2;
        document.getElementById('editOverlap').value = mission.overlap || 75;
        document.getElementById('editCameraAngle').value = mission.camera_angle || 90;
        
        // Safety settings
        document.getElementById('editMinBattery').value = mission.min_battery || 30;
        document.getElementById('editMaxDistance').value = mission.max_distance || 2000;
        document.getElementById('editObstacleAvoidance').checked = mission.obstacle_avoidance !== false;
        document.getElementById('editGeofencing').checked = mission.geofencing !== false;
        document.getElementById('editEmergencyRth').checked = mission.emergency_rth !== false;
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('editMissionModal'));
        modal.show();
        
    } catch (error) {
        console.error('Error loading mission for edit:', error);
        showToast(error.message, 'error');
    }
}

// Save edited mission
async function saveEditedMission() {
    const missionId = document.getElementById('editMissionId').value;
    
    const updateData = {
        name: document.getElementById('editMissionName').value.trim(),
        mission_type: document.getElementById('editMissionType').value,
        device_id: document.getElementById('editDeviceId').value.trim(),
        device_name: document.getElementById('editDeviceName').value.trim(),
        status: document.getElementById('editMissionStatus').value,
        description: document.getElementById('editMissionDescription').value.trim(),
        // Flight Parameters
        flight_height: parseFloat(document.getElementById('editFlightHeight').value),
        flight_speed: parseFloat(document.getElementById('editFlightSpeed').value),
        return_altitude: parseFloat(document.getElementById('editReturnAltitude').value),
        photo_interval: parseFloat(document.getElementById('editPhotoInterval').value),
        overlap: parseFloat(document.getElementById('editOverlap').value),
        camera_angle: parseFloat(document.getElementById('editCameraAngle').value),
        // Safety Settings
        min_battery: parseFloat(document.getElementById('editMinBattery').value),
        max_distance: parseFloat(document.getElementById('editMaxDistance').value),
        obstacle_avoidance: document.getElementById('editObstacleAvoidance').checked,
        geofencing: document.getElementById('editGeofencing').checked,
        emergency_rth: document.getElementById('editEmergencyRth').checked
    };
    
    // Validate
    if (!updateData.name) {
        showToast('Please enter mission name', 'error');
        return;
    }
    
    if (!updateData.device_id) {
        showToast('Please enter device ID', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/missions/${missionId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Failed to update mission');
        }
        
        showToast('Mission updated successfully', 'success');
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('editMissionModal'));
        modal.hide();
        
        // Reload missions
        await loadMissions();
        
    } catch (error) {
        console.error('Error updating mission:', error);
        showToast(error.message, 'error');
    }
}

// Pause mission
async function pauseMission(missionId) {
    if (!confirm('Are you sure you want to pause this mission?')) return;
    
    try {
        const response = await fetch(`/api/missions/${missionId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: 'paused' })
        });
        
        if (!response.ok) throw new Error('Failed to pause mission');
        
        showToast('Mission paused', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error pausing mission:', error);
        showToast(error.message, 'error');
    }
}

// Stop mission
async function stopMission(missionId) {
    if (!confirm('Are you sure you want to stop this mission?')) return;
    
    try {
        const response = await fetch(`/api/missions/${missionId}/complete`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Failed to stop mission');
        
        showToast('Mission stopped', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error stopping mission:', error);
        showToast(error.message, 'error');
    }
}

// Start mission
async function startMission(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}/start`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Failed to start mission');
        
        const mission = await response.json();
        showToast('Mission started', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error starting mission:', error);
        showToast(error.message, 'error');
    }
}

// Stop mission
async function stopMission(missionId) {
    if (!confirm('Are you sure you want to stop this mission?')) return;
    
    try {
        const response = await fetch(`/api/missions/${missionId}/complete`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Failed to stop mission');
        
        showToast('Mission stopped', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error stopping mission:', error);
        showToast(error.message, 'error');
    }
}

// Delete mission
async function deleteMission(missionId) {
    if (!confirm('Are you sure you want to delete this mission?')) return;
    
    try {
        const response = await fetch(`/api/missions/${missionId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete mission');
        
        showToast('Mission deleted', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error deleting mission:', error);
        showToast(error.message, 'error');
    }
}

// View mission details
// View mission route on map only
async function viewMissionRoute(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}`);
        if (!response.ok) throw new Error('Failed to load mission');
        
        const mission = await response.json();
        
        // Display on map
        displayMissionWaypoints(mission);
        showToast(`Showing route for: ${mission.name}`, 'success');
        
    } catch (error) {
        console.error('Error loading mission:', error);
        showToast(error.message, 'error');
    }
}

// Show mission detail modal only
async function showMissionDetailOnly(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}`);
        if (!response.ok) throw new Error('Failed to load mission');
        
        const mission = await response.json();
        
        // Show detail modal
        showMissionDetail(mission);
        
    } catch (error) {
        console.error('Error loading mission:', error);
        showToast(error.message, 'error');
    }
}

// View mission (both route and detail) - kept for backward compatibility
async function viewMission(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}`);
        if (!response.ok) throw new Error('Failed to load mission');
        
        const mission = await response.json();
        
        // Display on map
        displayMissionWaypoints(mission);
        
        // Show detail modal
        showMissionDetail(mission);
        
    } catch (error) {
        console.error('Error loading mission:', error);
        showToast(error.message, 'error');
    }
}

// Show mission detail modal
function showMissionDetail(mission) {
    const content = document.getElementById('missionDetailContent');
    
    const statusBadge = getStatusBadge(mission.status);
    const createdDate = new Date(mission.created_at).toLocaleString();
    const updatedDate = mission.updated_at ? new Date(mission.updated_at).toLocaleString() : 'N/A';
    
    content.innerHTML = `
        <div class="row">
            <!-- Left Column -->
            <div class="col-md-6">
                <h6 class="mb-3"><i class="fas fa-info-circle text-primary"></i> Basic Information</h6>
                <table class="table table-sm">
                    <tr>
                        <td class="text-muted" width="40%">Mission Name:</td>
                        <td><strong>${mission.name}</strong></td>
                    </tr>
                    <tr>
                        <td class="text-muted">Type:</td>
                        <td><span class="badge bg-info">${mission.mission_type}</span></td>
                    </tr>
                    <tr>
                        <td class="text-muted">Status:</td>
                        <td>${statusBadge}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Device ID:</td>
                        <td>${mission.device_id || 'N/A'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Device Name:</td>
                        <td>${mission.device_name || 'N/A'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Description:</td>
                        <td>${mission.description || 'No description'}</td>
                    </tr>
                </table>

                <h6 class="mb-3 mt-4"><i class="fas fa-plane text-primary"></i> Flight Parameters</h6>
                <table class="table table-sm">
                    <tr>
                        <td class="text-muted" width="40%">Flight Altitude:</td>
                        <td>${mission.flight_height || 50} m</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Flight Speed:</td>
                        <td>${mission.flight_speed || 5} m/s</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Return Altitude:</td>
                        <td>${mission.return_altitude || 70} m</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Photo Interval:</td>
                        <td>${mission.photo_interval || 2} s</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Photo Overlap:</td>
                        <td>${mission.overlap || 75} %</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Camera Angle:</td>
                        <td>${mission.camera_angle || 90}°</td>
                    </tr>
                </table>
            </div>

            <!-- Right Column -->
            <div class="col-md-6">
                <h6 class="mb-3"><i class="fas fa-shield-alt text-primary"></i> Safety Settings</h6>
                <table class="table table-sm">
                    <tr>
                        <td class="text-muted" width="40%">Min Battery RTH:</td>
                        <td>${mission.min_battery || 30} %</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Max Distance:</td>
                        <td>${mission.max_distance || 2000} m</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Obstacle Avoidance:</td>
                        <td>${mission.obstacle_avoidance ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Geofencing:</td>
                        <td>${mission.geofencing ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>'}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Emergency RTH:</td>
                        <td>${mission.emergency_rth ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>'}</td>
                    </tr>
                </table>

                <h6 class="mb-3 mt-4"><i class="fas fa-chart-line text-primary"></i> Mission Statistics</h6>
                <table class="table table-sm">
                    <tr>
                        <td class="text-muted" width="40%">Total Distance:</td>
                        <td><strong>${(mission.total_distance || 0).toFixed(2)} km</strong></td>
                    </tr>
                    <tr>
                        <td class="text-muted">Est. Duration:</td>
                        <td>${formatDuration(mission.estimated_duration || 0)}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Battery Required:</td>
                        <td>${(mission.battery_required || 0).toFixed(1)} %</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Waypoints:</td>
                        <td>${mission.waypoint_count || 0}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Photos Estimated:</td>
                        <td>${mission.photos_estimated || 0}</td>
                    </tr>
                </table>

                <h6 class="mb-3 mt-4"><i class="fas fa-clock text-primary"></i> Timestamps</h6>
                <table class="table table-sm">
                    <tr>
                        <td class="text-muted" width="40%">Created:</td>
                        <td>${createdDate}</td>
                    </tr>
                    <tr>
                        <td class="text-muted">Updated:</td>
                        <td>${updatedDate}</td>
                    </tr>
                    ${mission.actual_start ? `
                    <tr>
                        <td class="text-muted">Started:</td>
                        <td>${new Date(mission.actual_start).toLocaleString()}</td>
                    </tr>
                    ` : ''}
                    ${mission.actual_end ? `
                    <tr>
                        <td class="text-muted">Completed:</td>
                        <td>${new Date(mission.actual_end).toLocaleString()}</td>
                    </tr>
                    ` : ''}
                </table>
            </div>
        </div>

        ${mission.waypoints && mission.waypoints.length > 0 ? `
        <div class="row mt-4">
            <div class="col-12">
                <h6 class="mb-3"><i class="fas fa-route text-primary"></i> Waypoints (${mission.waypoints.length})</h6>
                <div class="table-responsive">
                    <table class="table table-sm table-hover">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Type</th>
                                <th>Latitude</th>
                                <th>Longitude</th>
                                <th>Altitude</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${mission.waypoints.map((wp, idx) => `
                            <tr>
                                <td>${idx + 1}</td>
                                <td><span class="badge bg-secondary">${wp.waypoint_type || 'point'}</span></td>
                                <td>${wp.latitude.toFixed(6)}</td>
                                <td>${wp.longitude.toFixed(6)}</td>
                                <td>${wp.altitude || 0} m</td>
                                <td>${wp.action || 'hover'}</td>
                            </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        ` : ''}
    `;
    
    // Setup buttons
    document.getElementById('btnEditFromDetail').onclick = function() {
        const detailModal = bootstrap.Modal.getInstance(document.getElementById('missionDetailModal'));
        detailModal.hide();
        editMission(mission.id);
    };
    
    document.getElementById('btnManageOrders').onclick = function() {
        const detailModal = bootstrap.Modal.getInstance(document.getElementById('missionDetailModal'));
        detailModal.hide();
        manageOrders(mission.id);
    };
    
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('missionDetailModal'));
    modal.show();
}

// Format duration in seconds to HH:MM:SS
function formatDuration(seconds) {
    if (!seconds) return '00:00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

// Optimize mission route
async function optimizeMissionRoute(missionId) {
    try {
        const response = await fetch(`/api/missions/${missionId}/optimize-route`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('Failed to optimize route');
        
        const result = await response.json();
        showToast('Route optimized successfully', 'success');
        await loadMissions();
        
    } catch (error) {
        console.error('Error optimizing route:', error);
        showToast(error.message, 'error');
    }
}

// Update mission statistics
function updateMissionStats() {
    let totalDistance = 0;
    let waypointCount = 0;
    
    drawnItems.eachLayer(function(layer) {
        if (layer instanceof L.Marker) {
            waypointCount++;
        } else if (layer instanceof L.Polyline) {
            const latlngs = layer.getLatLngs();
            for (let i = 1; i < latlngs.length; i++) {
                totalDistance += latlngs[i-1].distanceTo(latlngs[i]);
            }
            waypointCount += latlngs.length;
        }
    });
    
    // Convert to kilometers
    totalDistance = (totalDistance / 1000).toFixed(2);
    
    // Calculate duration
    const flightSpeed = parseFloat(document.getElementById('flightSpeed')?.value || 5);
    const durationSeconds = (totalDistance * 1000) / flightSpeed;
    const hours = Math.floor(durationSeconds / 3600);
    const minutes = Math.floor((durationSeconds % 3600) / 60);
    const seconds = Math.floor(durationSeconds % 60);
    
    // Calculate battery
    const batteryRequired = Math.min(Math.round((durationSeconds / 1200) * 100), 100);
    
    // Calculate photos
    const photoInterval = parseFloat(document.getElementById('photoInterval')?.value || 2);
    const photosEst = Math.round(durationSeconds / photoInterval);
    
    // Update display
    if (document.getElementById('totalDistance')) {
        document.getElementById('totalDistance').textContent = `${totalDistance} km`;
    }
    if (document.getElementById('estDuration')) {
        document.getElementById('estDuration').textContent = 
            `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
    if (document.getElementById('batteryRequired')) {
        document.getElementById('batteryRequired').textContent = `${batteryRequired}%`;
    }
    if (document.getElementById('photosEst')) {
        document.getElementById('photosEst').textContent = photosEst;
    }
}

// Update waypoint list
function updateWaypointList() {
    const waypointList = document.getElementById('waypointList');
    if (!waypointList) return;
    
    let html = '';
    let index = 1;
    
    drawnItems.eachLayer(function(layer) {
        if (layer instanceof L.Marker) {
            const latlng = layer.getLatLng();
            html += `
                <div class="waypoint-item">
                    <div class="d-flex justify-content-between">
                        <div class="d-flex align-items-center">
                            <i class="fas fa-map-marker-alt text-primary me-2"></i>
                            <div>
                                <div class="mb-1">Waypoint ${index}</div>
                                <small class="text-muted">${latlng.lat.toFixed(6)}°, ${latlng.lng.toFixed(6)}°</small>
                            </div>
                        </div>
                        <button class="btn btn-sm btn-link text-danger" onclick="removeWaypoint(${index - 1})">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
            index++;
        }
    });
    
    if (html === '') {
        html = '<p class="text-muted text-center py-3">No waypoints yet. Click on map to add.</p>';
    }
    
    waypointList.innerHTML = html;
}

// Clear mission
function clearMission() {
    if (!confirm('Clear all waypoints?')) return;
    
    drawnItems.clearLayers();
    activeMissionMarkers.forEach(marker => missionMap.removeLayer(marker));
    activeMissionMarkers = [];
    updateMissionStats();
    updateWaypointList();
}

// Setup event listeners
function setupEventListeners() {
    // Flight parameters change
    const params = ['flightSpeed', 'flightHeight', 'photoInterval'];
    params.forEach(id => {
        const elem = document.getElementById(id);
        if (elem) {
            elem.addEventListener('change', updateMissionStats);
        }
    });
}

// Connect WebSocket for real-time updates
function connectWebSocket() {
    if (typeof io === 'undefined') return;
    
    const socket = io();
    
    socket.on('mission_update', function(data) {
        console.log('Mission update:', data);
        loadMissions();
    });
    
    socket.on('waypoint_reached', function(data) {
        console.log('Waypoint reached:', data);
        showToast(`Waypoint ${data.waypoint_sequence} reached`, 'info');
    });
}

// Utility: Show toast notification
function showToast(message, type = 'info') {
    // Simple toast notification (you can replace with Bootstrap Toast or other library)
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} position-fixed top-0 end-0 m-3`;
    toast.style.zIndex = '9999';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Utility: Get time ago
function getTimeAgo(dateString) {
    if (!dateString) return 'just now';
    
    const date = new Date(dateString);
    const seconds = Math.floor((new Date() - date) / 1000);
    
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    return `${Math.floor(seconds / 86400)} days ago`;
}

// Set drawing mode
function setDrawingMode(mode) {
    // This function can be enhanced to programmatically trigger drawing
    console.log('Drawing mode:', mode);
}

// Save mission configuration
async function saveMissionConfig() {
    const config = {
        flight_altitude: parseFloat(document.getElementById('flightHeight').value),
        flight_speed: parseFloat(document.getElementById('flightSpeed').value),
        return_altitude: parseFloat(document.getElementById('returnAltitude').value),
        photo_interval: parseFloat(document.getElementById('photoInterval').value),
        overlap: parseFloat(document.getElementById('overlap').value),
        camera_angle: parseFloat(document.getElementById('cameraAngle').value),
        min_battery_rth: parseFloat(document.getElementById('minBattery').value),
        max_flight_distance: parseFloat(document.getElementById('maxDistance').value),
        enable_obstacle_avoidance: document.getElementById('obstacleAvoidance').checked,
        enable_geofencing: document.getElementById('geofencing').checked,
        emergency_rth_enabled: document.getElementById('emergencyRTH').checked
    };
    
    // Save to localStorage for now (you can add API endpoint later)
    localStorage.setItem('missionConfig', JSON.stringify(config));
    showToast('Configuration saved', 'success');
}

// Load saved configuration
function loadSavedConfig() {
    const saved = localStorage.getItem('missionConfig');
    if (!saved) return;
    
    try {
        const config = JSON.parse(saved);
        document.getElementById('flightHeight').value = config.flight_altitude || 50;
        document.getElementById('flightSpeed').value = config.flight_speed || 5;
        document.getElementById('returnAltitude').value = config.return_altitude || 70;
        document.getElementById('photoInterval').value = config.photo_interval || 2;
        document.getElementById('overlap').value = config.overlap || 75;
        document.getElementById('cameraAngle').value = config.camera_angle || 90;
        document.getElementById('minBattery').value = config.min_battery_rth || 30;
        document.getElementById('maxDistance').value = config.max_flight_distance || 2000;
        document.getElementById('obstacleAvoidance').checked = config.enable_obstacle_avoidance !== false;
        document.getElementById('geofencing').checked = config.enable_geofencing !== false;
        document.getElementById('emergencyRTH').checked = config.emergency_rth_enabled !== false;
    } catch (error) {
        console.error('Error loading saved config:', error);
    }
}

// Load saved config on page load
loadSavedConfig();

// ============================================
// ORDER MANAGEMENT FUNCTIONS
// ============================================

// Manage orders for a mission
async function manageOrders(missionId) {
    try {
        document.getElementById('orderMissionId').value = missionId;
        
        // Load orders for this mission
        await loadOrdersForMission(missionId);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('orderManagementModal'));
        modal.show();
        
    } catch (error) {
        console.error('Error opening order management:', error);
        showToast(error.message, 'error');
    }
}

// Load orders for a mission
async function loadOrdersForMission(missionId) {
    try {
        const response = await fetch(`/api/orders?mission_id=${missionId}`);
        if (!response.ok) throw new Error('Failed to load orders');
        
        const orders = await response.json();
        displayOrders(orders);
        
    } catch (error) {
        console.error('Error loading orders:', error);
        showToast(error.message, 'error');
    }
}

// Display orders list
function displayOrders(orders) {
    const container = document.getElementById('ordersListContainer');
    
    if (orders.length === 0) {
        container.innerHTML = '<p class="text-muted text-center py-3">No orders yet. Click "Add Order" to create one.</p>';
        return;
    }
    
    let html = '<div class="list-group">';
    orders.forEach(order => {
        const priorityBadge = getPriorityBadge(order.priority);
        const statusBadge = getOrderStatusBadge(order.status);
        const categoryIcon = getCategoryIcon(order.category);
        
        html += `
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">
                            ${categoryIcon} ${order.order_number}
                            ${priorityBadge}
                            ${statusBadge}
                        </h6>
                        <div class="small text-muted">
                            <i class="fas fa-map-marker-alt text-success"></i> Pickup: ${order.pickup_address || `${order.pickup_latitude}, ${order.pickup_longitude}`}
                        </div>
                        <div class="small text-muted">
                            <i class="fas fa-map-marker-alt text-danger"></i> Delivery: ${order.delivery_address || `${order.delivery_latitude}, ${order.delivery_longitude}`}
                        </div>
                        ${order.package_weight ? `<div class="small text-muted"><i class="fas fa-weight"></i> ${order.package_weight} kg</div>` : ''}
                        ${order.special_instructions ? `<div class="small text-muted"><i class="fas fa-info-circle"></i> ${order.special_instructions}</div>` : ''}
                    </div>
                    <div class="ms-3">
                        <button class="btn btn-sm btn-outline-info" onclick="viewOrderDetail(${order.id})">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteOrder(${order.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

// Get priority badge
function getPriorityBadge(priority) {
    const badges = {
        'low': '<span class="badge bg-secondary">Low</span>',
        'medium': '<span class="badge bg-info">Medium</span>',
        'high': '<span class="badge bg-warning">High</span>',
        'critical': '<span class="badge bg-danger">Critical</span>'
    };
    return badges[priority] || '';
}

// Get order status badge
function getOrderStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge bg-secondary">Pending</span>',
        'assigned': '<span class="badge bg-info">Assigned</span>',
        'picked_up': '<span class="badge bg-primary">Picked Up</span>',
        'in_transit': '<span class="badge bg-warning">In Transit</span>',
        'delivered': '<span class="badge bg-success">Delivered</span>',
        'cancelled': '<span class="badge bg-danger">Cancelled</span>',
        'failed': '<span class="badge bg-danger">Failed</span>'
    };
    return badges[status] || '';
}

// Get category icon
function getCategoryIcon(category) {
    const icons = {
        'food': '<i class="fas fa-utensils text-warning"></i>',
        'medical': '<i class="fas fa-medkit text-danger"></i>',
        'equipment': '<i class="fas fa-tools text-info"></i>',
        'documents': '<i class="fas fa-file-alt text-primary"></i>',
        'emergency': '<i class="fas fa-exclamation-triangle text-danger"></i>',
        'other': '<i class="fas fa-box text-secondary"></i>'
    };
    return icons[category] || icons['other'];
}

// Show add order form
function showAddOrderForm() {
    document.getElementById('addOrderForm').style.display = 'block';
    // Generate order number
    const orderNumber = 'ORD-' + Date.now();
    document.getElementById('newOrderNumber').value = orderNumber;
    
    // Load waypoints to delivery dropdown
    loadWaypointsToDeliverySelect('newDeliveryWaypoint');
}

// Hide add order form
function hideAddOrderForm() {
    document.getElementById('addOrderForm').style.display = 'none';
    clearOrderForm();
}

// Clear order form
function clearOrderForm() {
    document.getElementById('newOrderNumber').value = '';
    document.getElementById('newOrderCategory').value = 'food';
    document.getElementById('newOrderPriority').value = 'medium';
    document.getElementById('newPickupLat').value = '';
    document.getElementById('newPickupLng').value = '';
    document.getElementById('newPickupAddress').value = '';
    document.getElementById('newPickupContact').value = '';
    document.getElementById('newDeliveryLat').value = '';
    document.getElementById('newDeliveryLng').value = '';
    document.getElementById('newDeliveryAddress').value = '';
    document.getElementById('newDeliveryContact').value = '';
    document.getElementById('newPackageWeight').value = '';
    document.getElementById('newItemCount').value = '1';
    document.getElementById('newDeliveryFee').value = '0';
    document.getElementById('newSpecialInstructions').value = '';
    document.getElementById('newFragile').checked = false;
    document.getElementById('newTimeSensitive').checked = false;
    document.getElementById('newTempControlled').checked = false;
}

// Save new order
async function saveNewOrder() {
    const missionId = document.getElementById('orderMissionId').value;
    
    // Get pickup location
    const pickupSelect = document.getElementById('newPickupLocation');
    const pickupOption = pickupSelect.options[pickupSelect.selectedIndex];
    
    let pickupLat, pickupLng, pickupAddr;
    
    if (pickupSelect.value === 'custom') {
        pickupLat = parseFloat(document.getElementById('newPickupLat').value);
        pickupLng = parseFloat(document.getElementById('newPickupLng').value);
        pickupAddr = document.getElementById('newPickupAddress').value.trim();
    } else if (pickupSelect.value) {
        pickupLat = parseFloat(pickupOption.getAttribute('data-lat'));
        pickupLng = parseFloat(pickupOption.getAttribute('data-lng'));
        pickupAddr = pickupOption.textContent.replace(/📦|🏪|💊|🏭/g, '').trim();
    }
    
    // Get delivery location
    const deliveryCustomToggle = document.getElementById('newDeliveryCustomToggle');
    let deliveryLat, deliveryLng, deliveryAddr;
    
    if (deliveryCustomToggle.checked) {
        deliveryLat = parseFloat(document.getElementById('newDeliveryLat').value);
        deliveryLng = parseFloat(document.getElementById('newDeliveryLng').value);
        deliveryAddr = document.getElementById('newDeliveryAddress').value.trim();
    } else {
        const deliverySelect = document.getElementById('newDeliveryWaypoint');
        const deliveryOption = deliverySelect.options[deliverySelect.selectedIndex];
        if (deliverySelect.value) {
            deliveryLat = parseFloat(deliveryOption.getAttribute('data-lat'));
            deliveryLng = parseFloat(deliveryOption.getAttribute('data-lng'));
            deliveryAddr = 'Mission waypoint';
        }
    }
    
    const orderData = {
        mission_id: parseInt(missionId),
        order_number: document.getElementById('newOrderNumber').value,
        category: document.getElementById('newOrderCategory').value,
        priority: document.getElementById('newOrderPriority').value,
        pickup_latitude: pickupLat,
        pickup_longitude: pickupLng,
        pickup_address: pickupAddr,
        pickup_contact_name: document.getElementById('newPickupContact').value.trim(),
        delivery_latitude: deliveryLat,
        delivery_longitude: deliveryLng,
        delivery_address: deliveryAddr,
        delivery_contact_name: document.getElementById('newDeliveryContact').value.trim(),
        package_weight: parseFloat(document.getElementById('newPackageWeight').value) || null,
        item_count: parseInt(document.getElementById('newItemCount').value) || 1,
        delivery_fee: parseFloat(document.getElementById('newDeliveryFee').value) || 0,
        special_instructions: document.getElementById('newSpecialInstructions').value.trim(),
        fragile: document.getElementById('newFragile').checked,
        time_sensitive: document.getElementById('newTimeSensitive').checked,
        temperature_controlled: document.getElementById('newTempControlled').checked
    };
    
    // Validate
    if (!orderData.pickup_latitude || !orderData.pickup_longitude) {
        showToast('Please select pickup location', 'error');
        return;
    }
    
    if (!orderData.delivery_latitude || !orderData.delivery_longitude) {
        showToast('Please select delivery location', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(orderData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Failed to create order');
        }
        
        showToast('Order created successfully', 'success');
        hideAddOrderForm();
        await loadOrdersForMission(missionId);
        
    } catch (error) {
        console.error('Error creating order:', error);
        showToast(error.message, 'error');
    }
}

// Delete order
async function deleteOrder(orderId) {
    if (!confirm('Are you sure you want to delete this order?')) return;
    
    try {
        const response = await fetch(`/api/orders/${orderId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete order');
        
        showToast('Order deleted successfully', 'success');
        
        const missionId = document.getElementById('orderMissionId').value;
        await loadOrdersForMission(missionId);
        
    } catch (error) {
        console.error('Error deleting order:', error);
        showToast(error.message, 'error');
    }
}

// View order detail (placeholder)
function viewOrderDetail(orderId) {
    showToast('Order detail view coming soon', 'info');
    // TODO: Implement order detail modal
}

// ============================================
// QUICK ORDER FUNCTIONS (FOR MISSION CREATION)
// ============================================

// Setup toggle for orders section in mission modal
function setupModalOrdersToggle() {
    const checkbox = document.getElementById('modalAddOrders');
    const section = document.getElementById('modalOrdersSection');
    
    if (checkbox && section) {
        checkbox.addEventListener('change', function() {
            section.style.display = this.checked ? 'block' : 'none';
        });
    }
    
    // Setup pickup location toggle for quick order
    const quickPickupSelect = document.getElementById('quickPickupLocation');
    if (quickPickupSelect) {
        quickPickupSelect.addEventListener('change', function() {
            const customDiv = document.getElementById('quickPickupCustom');
            if (this.value === 'custom') {
                customDiv.style.display = 'block';
            } else {
                customDiv.style.display = 'none';
            }
        });
    }
    
    // Setup pickup location toggle for full order form
    const newPickupSelect = document.getElementById('newPickupLocation');
    if (newPickupSelect) {
        newPickupSelect.addEventListener('change', function() {
            const customDiv = document.getElementById('newPickupCustom');
            if (this.value === 'custom') {
                customDiv.style.display = 'block';
            } else {
                customDiv.style.display = 'none';
            }
        });
    }
    
    // Setup delivery custom toggle
    const deliveryCustomCheckbox = document.getElementById('newDeliveryCustomToggle');
    if (deliveryCustomCheckbox) {
        deliveryCustomCheckbox.addEventListener('change', function() {
            const customDiv = document.getElementById('newDeliveryCustom');
            const waypointSelect = document.getElementById('newDeliveryWaypoint');
            if (this.checked) {
                customDiv.style.display = 'block';
                waypointSelect.disabled = true;
            } else {
                customDiv.style.display = 'none';
                waypointSelect.disabled = false;
            }
        });
    }
}

// Add quick order
function addQuickOrder() {
    // Load waypoints from map into delivery dropdown
    loadWaypointsToDeliverySelect('quickDeliveryWaypoint');
    
    const modal = new bootstrap.Modal(document.getElementById('quickOrderModal'));
    modal.show();
}

// Load waypoints into select dropdown
function loadWaypointsToDeliverySelect(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    // Clear existing options except first
    select.innerHTML = '<option value="">-- Select delivery waypoint --</option>';
    
    let waypointIndex = 1;
    drawnItems.eachLayer(function(layer) {
        if (layer instanceof L.Marker) {
            const latlng = layer.getLatLng();
            const option = document.createElement('option');
            option.value = `${latlng.lat},${latlng.lng}`;
            option.textContent = `📍 Waypoint ${waypointIndex}: ${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
            option.setAttribute('data-lat', latlng.lat);
            option.setAttribute('data-lng', latlng.lng);
            select.appendChild(option);
            waypointIndex++;
        }
    });
    
    if (waypointIndex === 1) {
        const option = document.createElement('option');
        option.value = 'none';
        option.textContent = '⚠️ No waypoints on map yet';
        option.disabled = true;
        select.appendChild(option);
    }
}

// Save quick order (to temp list)
function saveQuickOrder() {
    // Get pickup location
    const pickupSelect = document.getElementById('quickPickupLocation');
    const pickupOption = pickupSelect.options[pickupSelect.selectedIndex];
    
    let pickupLat, pickupLng, pickupAddr;
    
    if (pickupSelect.value === 'custom') {
        pickupLat = parseFloat(document.getElementById('quickPickupLat').value);
        pickupLng = parseFloat(document.getElementById('quickPickupLng').value);
        pickupAddr = 'Custom location';
    } else if (pickupSelect.value) {
        pickupLat = parseFloat(pickupOption.getAttribute('data-lat'));
        pickupLng = parseFloat(pickupOption.getAttribute('data-lng'));
        pickupAddr = pickupOption.textContent.replace(/📦|🏪|💊|🏭/g, '').trim();
    }
    
    // Get delivery location
    const deliverySelect = document.getElementById('quickDeliveryWaypoint');
    const deliveryOption = deliverySelect.options[deliverySelect.selectedIndex];
    
    let deliveryLat, deliveryLng;
    
    if (deliverySelect.value) {
        deliveryLat = parseFloat(deliveryOption.getAttribute('data-lat'));
        deliveryLng = parseFloat(deliveryOption.getAttribute('data-lng'));
    }
    
    const order = {
        category: document.getElementById('quickOrderCategory').value,
        priority: document.getElementById('quickOrderPriority').value,
        pickup_latitude: pickupLat,
        pickup_longitude: pickupLng,
        pickup_address: pickupAddr,
        delivery_latitude: deliveryLat,
        delivery_longitude: deliveryLng,
        delivery_contact_name: document.getElementById('quickDeliveryContact').value.trim(),
        package_weight: parseFloat(document.getElementById('quickOrderWeight').value) || null,
        item_count: parseInt(document.getElementById('quickOrderItems').value) || 1,
        special_instructions: document.getElementById('quickOrderNotes').value.trim(),
        fragile: document.getElementById('quickOrderFragile').checked,
        time_sensitive: document.getElementById('quickOrderTimeSensitive').checked,
        temperature_controlled: document.getElementById('quickOrderTempControl').checked
    };
    
    // Validate
    if (!order.pickup_latitude || !order.pickup_longitude) {
        showToast('Please select pickup location', 'error');
        return;
    }
    
    if (!order.delivery_latitude || !order.delivery_longitude) {
        showToast('Please select delivery waypoint', 'error');
        return;
    }
    
    // Add to temp list
    tempOrders.push(order);
    
    // Update display
    updateQuickOrdersList();
    
    // Close modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('quickOrderModal'));
    modal.hide();
    
    // Clear form
    document.getElementById('quickPickupLat').value = '';
    document.getElementById('quickPickupLng').value = '';
    document.getElementById('quickDeliveryLat').value = '';
    document.getElementById('quickDeliveryLng').value = '';
    document.getElementById('quickOrderNotes').value = '';
    
    showToast('Order added to mission', 'success');
}

// Update quick orders list display
function updateQuickOrdersList() {
    const container = document.getElementById('modalOrdersList');
    
    if (tempOrders.length === 0) {
        container.innerHTML = '<p class="text-muted small mb-2">No orders added yet</p>';
        return;
    }
    
    let html = '<div class="small">';
    tempOrders.forEach((order, index) => {
        const icon = getCategoryIcon(order.category);
        html += `
            <div class="d-flex justify-content-between align-items-center mb-2 p-2" style="background: rgba(0,0,0,0.2); border-radius: 4px;">
                <span>${icon} ${order.category.toUpperCase()} - ${getPriorityBadge(order.priority)}</span>
                <button class="btn btn-sm btn-outline-danger" onclick="removeTempOrder(${index})">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

// Remove temp order
function removeTempOrder(index) {
    tempOrders.splice(index, 1);
    updateQuickOrdersList();
}

// Update createNewMission to include orders
async function createMissionWithOrders() {
    const missionData = {
        name: document.getElementById('missionName').value.trim(),
        mission_type: document.getElementById('newMissionType').value,
        description: document.getElementById('missionDescription').value.trim(),
        device_id: document.getElementById('modalDeviceId').value.trim(),
        device_name: document.getElementById('modalDeviceName').value.trim(),
        waypoints: [],
        // Flight Parameters
        flight_height: parseFloat(document.getElementById('modalFlightHeight').value),
        flight_speed: parseFloat(document.getElementById('modalFlightSpeed').value),
        return_altitude: parseFloat(document.getElementById('modalReturnAltitude').value),
        photo_interval: parseFloat(document.getElementById('modalPhotoInterval').value),
        overlap: parseFloat(document.getElementById('modalOverlap').value),
        camera_angle: parseFloat(document.getElementById('modalCameraAngle').value),
        // Safety Settings
        min_battery: parseFloat(document.getElementById('modalMinBattery').value),
        max_distance: parseFloat(document.getElementById('modalMaxDistance').value),
        obstacle_avoidance: document.getElementById('modalObstacleAvoidance').checked,
        geofencing: document.getElementById('modalGeofencing').checked,
        emergency_rth: document.getElementById('modalEmergencyRth').checked
    };
    
    // Validate required fields
    if (!missionData.name) {
        showToast('Please enter mission name', 'error');
        return;
    }
    
    if (!missionData.device_id) {
        showToast('Please enter device ID', 'error');
        return;
    }
    
    // Convert drawn items to waypoints
    let sequence = 1;
    drawnItems.eachLayer(function(layer) {
        if (layer instanceof L.Marker) {
            const latlng = layer.getLatLng();
            missionData.waypoints.push({
                latitude: latlng.lat,
                longitude: latlng.lng,
                altitude: missionData.flight_height,
                sequence: sequence++,
                action: 'hover',
                waypoint_type: 'point'
            });
        } else if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
            const latlngs = layer.getLatLngs();
            latlngs.forEach(latlng => {
                missionData.waypoints.push({
                    latitude: latlng.lat,
                    longitude: latlng.lng,
                    altitude: missionData.flight_height,
                    sequence: sequence++,
                    action: 'flyto',
                    waypoint_type: 'point'
                });
            });
        }
    });
    
    if (missionData.waypoints.length === 0) {
        showToast('Please add at least one waypoint', 'error');
        return;
    }
    
    try {
        // Create mission first
        const response = await fetch('/api/missions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(missionData)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Failed to create mission');
        }
        
        const result = await response.json();
        const newMission = result.mission;
        
        // Create orders if any
        if (tempOrders.length > 0) {
            for (const order of tempOrders) {
                order.mission_id = newMission.id;
                order.order_number = 'ORD-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
                
                await fetch('/api/orders', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(order)
                });
            }
            showToast(`Mission created with ${tempOrders.length} order(s)`, 'success');
        } else {
            showToast('Mission created successfully', 'success');
        }
        
        // Clear temp orders
        tempOrders = [];
        updateQuickOrdersList();
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('newMissionModal'));
        modal.hide();
        
        // Reload missions
        await loadMissions();
        
        // Clear form
        document.getElementById('missionName').value = '';
        document.getElementById('missionDescription').value = '';
        document.getElementById('modalAddOrders').checked = false;
        document.getElementById('modalOrdersSection').style.display = 'none';
        
    } catch (error) {
        console.error('Error creating mission:', error);
        showToast(error.message, 'error');
    }
}


