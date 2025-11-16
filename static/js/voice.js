/**
 * Voice Records Management - Client Side
 * Handles voice distress records display with map and list
 */

// Global variables
let voiceMap;
let allRecords = [];
let markers = [];

// HTML escape utility to prevent XSS
function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeMap();
    loadVoiceRecords();
    // Auto refresh every 30 seconds
    setInterval(loadVoiceRecords, 30000);
    
    // Add keyboard support for voice cards
    document.addEventListener('keydown', function(e) {
        if (e.target.classList.contains('voice-card') && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            e.target.click();
        }
    });
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

// Display records in sidebar (XSS-safe using DOM APIs)
function displayRecords(records) {
    const container = document.getElementById('voiceList');
    
    // Clear existing content
    container.innerHTML = '';
    
    if (records.length === 0) {
        const emptyMsg = document.createElement('p');
        emptyMsg.className = 'text-center text-muted py-3';
        emptyMsg.textContent = 'No voice records yet';
        container.appendChild(emptyMsg);
        return;
    }
    
    records.forEach(record => {
        // Create voice card element
        const card = document.createElement('div');
        card.className = 'voice-card p-3';
        
        // Add status classes
        if (record.is_resolved) {
            card.classList.add('voice-resolved');
        } else if (record.is_urgent) {
            card.classList.add('voice-urgent');
        }
        
        // Set accessibility attributes
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        const ariaLabel = record.is_resolved ? `Resolved: ${record.device_id}` : record.device_id;
        card.setAttribute('aria-label', ariaLabel);
        
        // Add click handler
        card.onclick = () => viewRecordDetail(record.id);
        
        // Add visually-hidden resolved indicator for screen readers
        if (record.is_resolved) {
            const hiddenSpan = document.createElement('span');
            hiddenSpan.className = 'visually-hidden';
            hiddenSpan.textContent = 'Resolved - ';
            card.appendChild(hiddenSpan);
        }
        
        // Create header row (device ID, date, priority badge)
        const headerRow = document.createElement('div');
        headerRow.className = 'd-flex justify-content-between align-items-start mb-2';
        
        const leftCol = document.createElement('div');
        
        const deviceHeading = document.createElement('h6');
        deviceHeading.className = 'mb-1';
        deviceHeading.textContent = record.device_id; // Safe: textContent escapes HTML
        leftCol.appendChild(deviceHeading);
        
        const dateSmall = document.createElement('small');
        dateSmall.className = 'text-muted';
        const recordDate = new Date(record.recorded_at).toLocaleString();
        dateSmall.textContent = recordDate;
        leftCol.appendChild(dateSmall);
        
        headerRow.appendChild(leftCol);
        headerRow.appendChild(createPriorityBadgeElement(record.priority));
        card.appendChild(headerRow);
        
        // Add transcribed text preview if available
        if (record.transcribed_text) {
            const transcriptDiv = document.createElement('div');
            transcriptDiv.className = 'small mb-2';
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-comment-dots';
            transcriptDiv.appendChild(icon);
            
            const textNode = document.createTextNode(' "' + record.transcribed_text.substring(0, 60) + '..."');
            transcriptDiv.appendChild(textNode);
            
            card.appendChild(transcriptDiv);
        }
        
        // Add analysis intent if available
        if (record.analysis_intent) {
            const intentDiv = document.createElement('div');
            intentDiv.className = 'small mb-2';
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-brain';
            intentDiv.appendChild(icon);
            
            intentDiv.appendChild(document.createTextNode(' Intent: '));
            
            const strongIntent = document.createElement('strong');
            strongIntent.textContent = record.analysis_intent; // Safe: textContent escapes HTML
            intentDiv.appendChild(strongIntent);
            
            card.appendChild(intentDiv);
        }
        
        // Add analysis items if available
        if (record.analysis_items && Array.isArray(record.analysis_items) && record.analysis_items.length > 0) {
            const itemsDiv = document.createElement('div');
            itemsDiv.className = 'small mb-2';
            
            const icon = document.createElement('i');
            icon.className = 'fas fa-list';
            itemsDiv.appendChild(icon);
            
            itemsDiv.appendChild(document.createTextNode(' Items: '));
            
            const itemsText = document.createElement('span');
            itemsText.className = 'text-info';
            itemsText.textContent = record.analysis_items.join(', '); // Safe: textContent escapes HTML
            itemsDiv.appendChild(itemsText);
            
            card.appendChild(itemsDiv);
        }
        
        // Create badges row
        const badgesRow = document.createElement('div');
        badgesRow.className = 'd-flex gap-2 flex-wrap';
        
        badgesRow.appendChild(createTranscriptionBadgeElement(record.transcription_status));
        badgesRow.appendChild(createAnalysisBadgeElement(record.analysis_status));
        
        if (record.is_resolved) {
            const resolvedBadge = document.createElement('span');
            resolvedBadge.className = 'badge bg-success';
            resolvedBadge.textContent = 'Resolved';
            badgesRow.appendChild(resolvedBadge);
        }
        
        card.appendChild(badgesRow);
        container.appendChild(card);
    });
}

// Create priority badge as DOM element (XSS-safe)
function createPriorityBadgeElement(priority) {
    const badge = document.createElement('span');
    badge.className = 'badge';
    
    const badgeConfig = {
        'low': { class: 'bg-secondary', text: 'Low' },
        'medium': { class: 'bg-info', text: 'Medium' },
        'high': { class: 'bg-warning', text: 'High' },
        'critical': { class: 'bg-danger', text: 'Critical' }
    };
    
    const config = badgeConfig[priority] || { class: 'bg-secondary', text: 'Unknown' };
    badge.classList.add(config.class);
    badge.textContent = config.text;
    
    return badge;
}

// Create transcription status badge as DOM element (XSS-safe)
function createTranscriptionBadgeElement(status) {
    const badge = document.createElement('span');
    badge.className = 'status-badge badge';
    
    const statusConfig = {
        'pending': { class: 'bg-secondary', text: 'Transcribing...' },
        'completed': { class: 'bg-success', text: 'Transcribed' },
        'failed': { class: 'bg-danger', text: 'Failed' }
    };
    
    const config = statusConfig[status] || { class: 'bg-secondary', text: 'Unknown' };
    badge.classList.add(config.class);
    badge.textContent = config.text;
    
    return badge;
}

// Create analysis status badge as DOM element (XSS-safe)
function createAnalysisBadgeElement(status) {
    const badge = document.createElement('span');
    badge.className = 'status-badge badge';
    
    const statusConfig = {
        'pending': { class: 'bg-secondary', text: 'Analyzing...' },
        'processing': { class: 'bg-info', text: 'Processing...' },
        'completed': { class: 'bg-success', text: 'Analyzed' },
        'failed': { class: 'bg-danger', text: 'Failed' }
    };
    
    const config = statusConfig[status] || { class: 'bg-secondary', text: 'Unknown' };
    badge.classList.add(config.class);
    badge.textContent = config.text;
    
    return badge;
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
        
        // Build popup with escaped user data
        const popupText = record.transcribed_text 
            ? escapeHtml(record.transcribed_text.substring(0, 100)) + '...' 
            : 'Transcribing...';
        
        marker.bindPopup(`
            <b>${escapeHtml(record.device_id)}</b><br>
            ${popupText}
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

// Show record detail in modal (XSS-safe with escaped user data)
function showRecordDetail(record) {
    const content = document.getElementById('voiceDetailContent');
    const recordDate = new Date(record.recorded_at).toLocaleString();
    
    // Build intent row if available
    const intentRow = record.analysis_intent ? `
        <tr>
            <td>Intent:</td>
            <td><strong>${escapeHtml(record.analysis_intent)}</strong></td>
        </tr>
    ` : '';
    
    // Build items row if available
    const itemsRow = (record.analysis_items && record.analysis_items.length > 0) ? `
        <tr>
            <td>Items Needed:</td>
            <td>${escapeHtml(record.analysis_items.join(', '))}</td>
        </tr>
    ` : '';
    
    // Build transcribed text section if available
    const transcribedSection = record.transcribed_text ? `
        <div class="mt-3">
            <h6><i class="fas fa-comment-dots text-primary"></i> Transcribed Text</h6>
            <div class="alert alert-info">
                ${escapeHtml(record.transcribed_text)}
            </div>
        </div>
    ` : '';
    
    // Build operator notes section if available
    const notesSection = record.operator_notes ? `
        <div class="mt-3">
            <h6><i class="fas fa-sticky-note text-primary"></i> Operator Notes</h6>
            <div class="alert alert-secondary">
                ${escapeHtml(record.operator_notes)}
            </div>
        </div>
    ` : '';
    
    content.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <h6><i class="fas fa-info-circle text-primary"></i> Basic Information</h6>
                <table class="table table-sm table-dark">
                    <tr>
                        <td>Device ID:</td>
                        <td><strong>${escapeHtml(record.device_id)}</strong></td>
                    </tr>
                    <tr>
                        <td>Recorded:</td>
                        <td>${escapeHtml(recordDate)}</td>
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
                    ${intentRow}
                    ${itemsRow}
                </table>
            </div>
        </div>
        
        <div class="mt-3">
            <h6><i class="fas fa-volume-up text-primary"></i> Audio Recording</h6>
            <audio controls class="audio-player">
                <source src="${(record.audio_url)}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
        </div>
        
        ${transcribedSection}
        ${notesSection}
    `;
    
    // Setup buttons
    document.getElementById('btnResolveRecord').onclick = () => resolveRecord(record.id);
    document.getElementById('btnDeleteRecord').onclick = () => deleteRecord(record.id);
    
    const modal = new bootstrap.Modal(document.getElementById('voiceDetailModal'));
    modal.show();
}

// Show resolve modal with form for notes
function showResolveModal(recordId) {
    // Remove any existing resolve modal to avoid duplicate IDs
    const existingModal = document.getElementById('resolveModal');
    if (existingModal) {
        existingModal.remove();
    }
    
    // Create modal HTML
    const modalHTML = `
        <div class="modal fade" id="resolveModal" tabindex="-1" aria-labelledby="resolveModalLabel" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content bg-dark text-light">
                    <div class="modal-header">
                        <h5 class="modal-title" id="resolveModalLabel">
                            <i class="fas fa-check-circle text-success"></i> Resolve Voice Record
                        </h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <p>Mark this voice record as resolved. You can optionally add notes about the resolution.</p>
                        <div class="mb-3">
                            <label for="resolveNotes" class="form-label">Resolution Notes (Optional)</label>
                            <textarea class="form-control" id="resolveNotes" rows="3" 
                                      placeholder="e.g., Rescue team dispatched, supplies delivered, etc."></textarea>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-success" id="btnConfirmResolve">
                            <i class="fas fa-check"></i> Resolve
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Inject modal into DOM
    document.body.insertAdjacentHTML('beforeend', modalHTML);
    
    const modalElement = document.getElementById('resolveModal');
    const modal = new bootstrap.Modal(modalElement);
    
    // Wire up Resolve button
    document.getElementById('btnConfirmResolve').onclick = async () => {
        const notes = document.getElementById('resolveNotes').value.trim();
        await submitResolveRecord(recordId, notes, modal, modalElement);
    };
    
    // Clean up modal element when hidden
    modalElement.addEventListener('hidden.bs.modal', () => {
        modalElement.remove();
    });
    
    modal.show();
}

// Submit resolve record request
async function submitResolveRecord(recordId, notes, modal, modalElement) {
    try {
        const response = await fetch(`/api/voice/records/${recordId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({notes: notes || null})
        });
        
        // Check HTTP status before parsing JSON
        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `Server error: ${response.status}`;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.message || errorMessage;
            } catch (e) {
                // If response is not JSON, use status text
                errorMessage = `${response.status} ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            showToast('Record marked as resolved', 'success');
            
            // Hide resolve modal
            modal.hide();
            
            // Hide detail modal if it exists
            const detailModalElement = document.getElementById('voiceDetailModal');
            if (detailModalElement) {
                const detailModalInstance = bootstrap.Modal.getInstance(detailModalElement);
                if (detailModalInstance) {
                    detailModalInstance.hide();
                }
            }
            
            // Reload records
            loadVoiceRecords();
        } else {
            throw new Error(data.message || 'Unknown error occurred');
        }
    } catch (error) {
        console.error('Error resolving record:', error);
        showToast(`Error resolving record: ${error.message}`, 'danger');
    }
}

// Resolve record (now delegates to modal)
function resolveRecord(recordId) {
    showResolveModal(recordId);
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
