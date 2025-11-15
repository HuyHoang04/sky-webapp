/**
 * Voice Records Management - Client Side
 * Handles voice distress records display with map and list
 */

// Global variables
let voiceMap;
let allRecords = [];
let markers = [];

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadVoiceRecords();
    // Auto refresh every 30 seconds
    setInterval(loadVoiceRecords, 30000);
});

// Initialize Leaflet Map
function initializeMap() {
    voiceMap = L.map('voice-map').setView([21.0285, 105.8542], 13);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(voiceMap);
}

// Load voice records from API
async function loadVoiceRecords() {
    try {
        const response = await fetch('/api/voice/records');
        const data = await response.json();
        
        if (data.status === 'success') {
            allRecords = data.records;
            displayRecords(allRecords);
            displayMarkersOnMap(allRecords);
        }
    } catch (error) {
        console.error('Error loading voice records:', error);
        showToast('Error loading records', 'error');
    }
}

// Display records in sidebar
function displayRecords(records) {
    const container = document.getElementById('voiceList');
    
    if (records.length === 0) {
        container.innerHTML = '<p class="text-center text-muted py-3">No voice records yet</p>';
        return;
    }
    
    let html = '';
    records.forEach(record => {
        const statusClass = record.is_resolved ? 'voice-resolved' : (record.is_urgent ? 'voice-urgent' : '');
        const recordDate = new Date(record.recorded_at).toLocaleString();
        const priorityBadge = getPriorityBadge(record.priority);
        const transcriptionStatus = getTranscriptionBadge(record.transcription_status);
        const analysisStatus = getAnalysisBadge(record.analysis_status);
        
        html += `
            <div class="voice-card ${statusClass} p-3" onclick="viewRecordDetail(${record.id})">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <h6 class="mb-1">${record.device_id}</h6>
                        <small class="text-muted">${recordDate}</small>
                    </div>
                    ${priorityBadge}
                </div>
                
                ${record.transcribed_text ? `
                    <div class="small mb-2">
                        <i class="fas fa-comment-dots"></i> "${record.transcribed_text.substring(0, 60)}..."
                    </div>
                ` : ''}
                
                ${record.analysis_intent ? `
                    <div class="small mb-2">
                        <i class="fas fa-brain"></i> Intent: <strong>${record.analysis_intent}</strong>
                    </div>
                ` : ''}
                
                <div class="d-flex gap-2 flex-wrap">
                    ${transcriptionStatus}
                    ${analysisStatus}
                    ${record.is_resolved ? '<span class="badge bg-success">Resolved</span>' : ''}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

// Display markers on map
function displayMarkersOnMap(records) {
    // Clear existing markers
    markers.forEach(marker => voiceMap.removeLayer(marker));
    markers = [];
    
    records.forEach(record => {
        const iconColor = record.is_resolved ? '#52c41a' : (record.is_urgent ? '#ff4d4f' : '#faad14');
        
        const marker = L.marker([record.latitude, record.longitude], {
            icon: L.divIcon({
                className: 'custom-div-icon',
                html: `<div style="background-color: ${iconColor}; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid white;">
                    <i class="fas fa-microphone"></i>
                </div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            })
        });
        
        marker.bindPopup(`
            <b>${record.device_id}</b><br>
            ${record.transcribed_text ? record.transcribed_text.substring(0, 100) + '...' : 'Transcribing...'}
            <br><button class="btn btn-sm btn-info mt-2" onclick="viewRecordDetail(${record.id})">View Detail</button>
        `);
        
        marker.addTo(voiceMap);
        markers.push(marker);
    });
    
    // Fit map to show all markers
    if (markers.length > 0) {
        const group = new L.featureGroup(markers);
        voiceMap.fitBounds(group.getBounds().pad(0.1));
    }
}

// View record detail
async function viewRecordDetail(recordId) {
    try {
        const response = await fetch(`/api/voice/records/${recordId}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            showRecordDetail(data.record);
        }
    } catch (error) {
        console.error('Error loading record detail:', error);
        showToast('Error loading record detail', 'error');
    }
}

// Show record detail in modal
function showRecordDetail(record) {
    const content = document.getElementById('voiceDetailContent');
    const recordDate = new Date(record.recorded_at).toLocaleString();
    
    content.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <h6><i class="fas fa-info-circle text-primary"></i> Basic Information</h6>
                <table class="table table-sm table-dark">
                    <tr>
                        <td>Device ID:</td>
                        <td><strong>${record.device_id}</strong></td>
                    </tr>
                    <tr>
                        <td>Recorded:</td>
                        <td>${recordDate}</td>
                    </tr>
                    <tr>
                        <td>Location:</td>
                        <td>Lat: ${record.latitude.toFixed(6)}, Lng: ${record.longitude.toFixed(6)}</td>
                    </tr>
                    <tr>
                        <td>Priority:</td>
                        <td>${getPriorityBadge(record.priority)}</td>
                    </tr>
                    <tr>
                        <td>Status:</td>
                        <td>${record.is_resolved ? '<span class="badge bg-success">Resolved</span>' : '<span class="badge bg-warning">Pending</span>'}</td>
                    </tr>
                </table>
            </div>
            
            <div class="col-md-6">
                <h6><i class="fas fa-brain text-primary"></i> AI Analysis</h6>
                <table class="table table-sm table-dark">
                    <tr>
                        <td>Transcription:</td>
                        <td>${getTranscriptionBadge(record.transcription_status)}</td>
                    </tr>
                    <tr>
                        <td>Analysis:</td>
                        <td>${getAnalysisBadge(record.analysis_status)}</td>
                    </tr>
                    ${record.analysis_intent ? `
                        <tr>
                            <td>Intent:</td>
                            <td><strong>${record.analysis_intent}</strong></td>
                        </tr>
                    ` : ''}
                    ${record.analysis_items && record.analysis_items.length > 0 ? `
                        <tr>
                            <td>Items Needed:</td>
                            <td>${record.analysis_items.join(', ')}</td>
                        </tr>
                    ` : ''}
                </table>
            </div>
        </div>
        
        <div class="mt-3">
            <h6><i class="fas fa-volume-up text-primary"></i> Audio Recording</h6>
            <audio controls class="audio-player">
                <source src="${record.audio_url}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
        </div>
        
        ${record.transcribed_text ? `
            <div class="mt-3">
                <h6><i class="fas fa-comment-dots text-primary"></i> Transcribed Text</h6>
                <div class="alert alert-info">
                    ${record.transcribed_text}
                </div>
            </div>
        ` : ''}
        
        ${record.operator_notes ? `
            <div class="mt-3">
                <h6><i class="fas fa-sticky-note text-primary"></i> Operator Notes</h6>
                <div class="alert alert-secondary">
                    ${record.operator_notes}
                </div>
            </div>
        ` : ''}
    `;
    
    // Setup buttons
    document.getElementById('btnResolveRecord').onclick = () => resolveRecord(record.id);
    document.getElementById('btnDeleteRecord').onclick = () => deleteRecord(record.id);
    
    const modal = new bootstrap.Modal(document.getElementById('voiceDetailModal'));
    modal.show();
}

// Resolve record
async function resolveRecord(recordId) {
    const notes = prompt('Add resolution notes (optional):');
    
    try {
        const response = await fetch(`/api/voice/records/${recordId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({notes})
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showToast('Record marked as resolved', 'success');
            bootstrap.Modal.getInstance(document.getElementById('voiceDetailModal')).hide();
            loadVoiceRecords();
        }
    } catch (error) {
        showToast('Error resolving record', 'error');
    }
}

// Delete record
async function deleteRecord(recordId) {
    if (!confirm('Are you sure you want to delete this record?')) return;
    
    try {
        const response = await fetch(`/api/voice/records/${recordId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showToast('Record deleted', 'success');
            bootstrap.Modal.getInstance(document.getElementById('voiceDetailModal')).hide();
            loadVoiceRecords();
        }
    } catch (error) {
        showToast('Error deleting record', 'error');
    }
}

// Helper functions
function getPriorityBadge(priority) {
    const badges = {
        'low': '<span class="badge bg-secondary">Low</span>',
        'medium': '<span class="badge bg-info">Medium</span>',
        'high': '<span class="badge bg-warning">High</span>',
        'critical': '<span class="badge bg-danger">Critical</span>'
    };
    return badges[priority] || '<span class="badge bg-secondary">Unknown</span>';
}

function getTranscriptionBadge(status) {
    const badges = {
        'pending': '<span class="status-badge badge bg-secondary">Transcribing...</span>',
        'completed': '<span class="status-badge badge bg-success">Transcribed</span>',
        'failed': '<span class="status-badge badge bg-danger">Failed</span>'
    };
    return badges[status] || '<span class="status-badge badge bg-secondary">Unknown</span>';
}

function getAnalysisBadge(status) {
    const badges = {
        'pending': '<span class="status-badge badge bg-secondary">Analyzing...</span>',
        'processing': '<span class="status-badge badge bg-info">Processing...</span>',
        'completed': '<span class="status-badge badge bg-success">Analyzed</span>',
        'failed': '<span class="status-badge badge bg-danger">Failed</span>'
    };
    return badges[status] || '<span class="status-badge badge bg-secondary">Unknown</span>';
}

function showToast(message, type = 'info') {
    // Simple toast notification
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} position-fixed top-0 end-0 m-3`;
    toast.style.zIndex = '9999';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
