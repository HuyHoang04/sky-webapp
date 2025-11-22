/**
 * Video Layout Manager for Sky WebApp
 * Handles switching between different video layout modes and managing multiple video streams
 */

class VideoLayoutManager {
    constructor() {
        this.container = document.getElementById('videoContainer');
        this.grid = document.getElementById('videoGrid');
        this.viewLayoutList = document.getElementById('viewLayoutList');
        this.videoSourceDropdown = document.getElementById('videoSourceDropdown');
        this.videoSourceList = document.getElementById('videoSourceList');
        this.webrtcClients = new Map(); // Map to store WebRTC clients for each video
        this.devices = new Set(); // Set to track all devices (mock + real)
        this.mockDevices = ['drone1', 'drone2']; // Mock devices to initialize

        this.setupLayoutSwitcher();
        this.initializeDevices();
        this.setupSocketIO();
    }

    setupLayoutSwitcher() {
        if (this.viewLayoutList) {
            this.viewLayoutList.addEventListener('click', (event) => {
                const link = event.target.closest('a[data-layout]');
                if (link) {
                    const layout = link.getAttribute('data-layout');
                    this.switchLayout(layout);
                    
                    // Update active state
                    this.viewLayoutList.querySelectorAll('a').forEach(a => a.classList.remove('active'));
                    link.classList.add('active');
                }
            });
        }
    }

    async initializeDevices() {
        try {
            // Initialize mock devices first
            this.initializeMockDevices();
            
            // Fetch real devices from API
            await this.fetchRealDevices();
            
            // Initialize WebRTC clients for all devices
            await this.initializeWebRTCClients();
            
        } catch (error) {
            console.error('Error initializing devices:', error);
        }
    }

    initializeMockDevices() {
        // Add mock devices to prevent duplicates
        this.mockDevices.forEach(deviceId => {
            if (!this.devices.has(deviceId)) {
                this.devices.add(deviceId);
                this.createVideoCell(deviceId, `Drone ${deviceId.slice(-1)}`);
                this.addDeviceToDropdown(deviceId, `Drone ${deviceId.slice(-1)}`);
            }
        });
        
        // Update layout options after adding mock devices
        this.updateLayoutOptions();
    }

    async fetchRealDevices() {
        try {
            const response = await fetch('/api/video/streams');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const streams = await response.json();
            
            // Add real devices after mock devices
            for (const [deviceId, stream] of Object.entries(streams)) {
                if (!this.devices.has(deviceId)) {
                    this.devices.add(deviceId);
                    const deviceName = stream.device_name || deviceId.charAt(0).toUpperCase() + deviceId.slice(1);
                    this.createVideoCell(deviceId, deviceName);
                    this.addDeviceToDropdown(deviceId, deviceName);
                }
            }
            
            // Update layout options after adding real devices
            this.updateLayoutOptions();
            
        } catch (error) {
            console.error('Error fetching real devices:', error);
        }
    }

    setupSocketIO() {
        if (!window.socket) {
            console.warn('Socket.IO not available');
            return;
        }

        // Listen for new video devices
        window.socket.on('video_device_added', (data) => {
            this.handleNewDevice(data);
        });

        // Listen for device removal
        window.socket.on('video_device_removed', (data) => {
            this.handleDeviceRemoval(data);
        });
    }

    handleNewDevice(data) {
        const deviceId = data.device_id;
        const deviceName = data.device_name || deviceId.charAt(0).toUpperCase() + deviceId.slice(1);
        
        console.log(`📱 New device registered: ${deviceId} (${deviceName})`);
        
        // Prevent duplicates
        if (this.devices.has(deviceId)) {
            console.log(`ℹ️ Device ${deviceId} already exists, skipping...`);
            return;
        }
        
        this.devices.add(deviceId);
        this.createVideoCell(deviceId, deviceName);
        this.addDeviceToDropdown(deviceId, deviceName);
        
        // Update layout options
        this.updateLayoutOptions();
        
        // Initialize WebRTC client for new device
        console.log(`🔄 Initializing WebRTC for new device: ${deviceId}`);
        this.initializeWebRTCClient(deviceId);
        
        // Request drone to start streaming
        if (window.socket) {
            console.log(`📤 Requesting ${deviceId} to start WebRTC streaming`);
            window.socket.emit('start_webrtc', { device_id: deviceId });
        }
    }

    handleDeviceRemoval(data) {
        const deviceId = data.device_id;
        
        if (this.devices.has(deviceId)) {
            this.devices.delete(deviceId);
            this.removeVideoCell(deviceId);
            this.removeDeviceFromDropdown(deviceId);
            
            // Update layout options
            this.updateLayoutOptions();
            
            // Clean up WebRTC client
            if (this.webrtcClients.has(deviceId)) {
                this.webrtcClients.get(deviceId).stop();
                this.webrtcClients.delete(deviceId);
            }
        }
    }

    createVideoCell(deviceId, deviceName) {
        // Check if video cell already exists
        const existingCell = this.grid.querySelector(`[data-drone="${deviceId}"]`);
        if (existingCell) {
            console.log(`Video cell for ${deviceId} already exists`);
            return;
        }
        
        const videoCell = document.createElement('div');
        videoCell.className = 'video-cell';
        videoCell.setAttribute('data-drone', deviceId);
        
        // Create unique video element ID
        const videoId = `videoStream${deviceId.replace(/\D/g, '') || '1'}`;
        
        videoCell.innerHTML = `
            <video id="${videoId}" autoplay playsinline muted style="background-color: #000;"></video>
            <div class="video-stats">
                <div>
                    <i class="fas fa-signal"></i>
                    <span id="connectionQuality${deviceId.replace(/\D/g, '') || '1'}">Connecting...</span>
                </div>
            </div>
            <div class="video-label">${deviceName}</div>
        `;
        
        this.grid.appendChild(videoCell);
        
        console.log(`✅ Created video cell for device: ${deviceId} with video ID: ${videoId}`);
    }

    removeVideoCell(deviceId) {
        const videoCell = this.grid.querySelector(`[data-drone="${deviceId}"]`);
        if (videoCell) {
            videoCell.remove();
        }
    }

    addDeviceToDropdown(deviceId, deviceName) {
        // Check if device already exists in dropdown
        const existingItem = this.videoSourceList.querySelector(`[data-device-id="${deviceId}"]`);
        if (existingItem) {
            return;
        }
        
        const listItem = document.createElement('li');
        listItem.innerHTML = `<a class="dropdown-item" href="#" data-device-id="${deviceId}">${deviceName}</a>`;
        
        // Remove "No devices found" message if it exists
        const noDevicesMessage = this.videoSourceList.querySelector('.disabled');
        if (noDevicesMessage) {
            noDevicesMessage.parentElement.remove();
        }
        
        this.videoSourceList.appendChild(listItem);
        
        // Add click event listener
        listItem.querySelector('a').addEventListener('click', (e) => {
            e.preventDefault();
            this.selectVideoSource(deviceId, deviceName);
        });
    }

    removeDeviceFromDropdown(deviceId) {
        const dropdownItem = this.videoSourceList.querySelector(`[data-device-id="${deviceId}"]`);
        if (dropdownItem) {
            dropdownItem.parentElement.remove();
        }
        
        // If no devices left, show "No devices found" message
        if (this.videoSourceList.children.length === 0) {
            const noDevicesItem = document.createElement('li');
            noDevicesItem.innerHTML = '<a class="dropdown-item disabled" href="#">No devices found</a>';
            this.videoSourceList.appendChild(noDevicesItem);
        }
    }

    selectVideoSource(deviceId, deviceName) {
        this.videoSourceDropdown.textContent = deviceName;
        this.videoSourceDropdown.setAttribute('data-device-id', deviceId);
        
        // Stop current stream if exists
        if (window.peerConnection) {
            window.peerConnection.close();
            window.peerConnection = null;
        }
        
        // Start new stream
        if (window.startWebRTC) {
            window.startWebRTC(deviceId);
        }
    }

    updateLayoutOptions() {
        // Remove existing device-specific options
        const existingDeviceOptions = this.viewLayoutList.querySelectorAll('[data-device-id]');
        existingDeviceOptions.forEach(option => option.remove());
        
        // Remove existing divider
        const existingDivider = this.viewLayoutList.querySelector('.dropdown-divider');
        if (existingDivider) {
            existingDivider.remove();
        }
        
        // Add divider if we have devices
        if (this.devices.size > 0) {
            const divider = document.createElement('li');
            divider.innerHTML = '<hr class="dropdown-divider">';
            this.viewLayoutList.appendChild(divider);
            
            // Add device-specific options
            this.devices.forEach(deviceId => {
                const deviceName = deviceId.charAt(0).toUpperCase() + deviceId.slice(1);
                const listItem = document.createElement('li');
                listItem.innerHTML = `<a class="dropdown-item" href="#" data-layout="${deviceId}" data-device-id="${deviceId}"><i class="fas fa-drone me-2"></i>${deviceName}</a>`;
                this.viewLayoutList.appendChild(listItem);
                
                // Add click event listener
                listItem.querySelector('a').addEventListener('click', (e) => {
                    e.preventDefault();
                    this.switchLayout(deviceId);
                    
                    // Update active state
                    document.querySelectorAll('#viewLayoutList a').forEach(a => {
                        a.classList.remove('active');
                    });
                    e.target.classList.add('active');
                });
            });
        }
    }

    switchLayout(layout) {
        // Remove all layout classes
        this.container.classList.remove('single-view', 'grid-view');

        // Clear active state from all cells
        const cells = document.querySelectorAll('.video-cell');
        cells.forEach(cell => cell.classList.remove('active'));

        switch (layout) {
            case 'grid':
                this.container.classList.add('grid-view');
                cells.forEach(cell => cell.classList.add('active'));
                break;
            default: // single view or specific device
                this.container.classList.add('single-view');
                // If layout matches a device ID, show that specific device
                const targetCell = document.querySelector(`[data-drone="${layout}"]`);
                if (targetCell) {
                    targetCell.classList.add('active');
                } else {
                    // Fallback to first available device
                    const firstCell = document.querySelector('.video-cell');
                    if (firstCell) firstCell.classList.add('active');
                }
                break;
        }

        // Force video resize event
        window.dispatchEvent(new Event('resize'));
    }

    async initializeWebRTCClients() {
        // Initialize WebRTC clients for all current devices
        for (const deviceId of this.devices) {
            await this.initializeWebRTCClient(deviceId);
        }
    }

    async initializeWebRTCClient(deviceId) {
        try {
            console.log(`🚀 Initializing WebRTC client for device: ${deviceId}`);
            
            // Find the video element for this device
            const videoCell = this.grid.querySelector(`[data-drone="${deviceId}"]`);
            if (!videoCell) {
                console.warn(`❌ Video cell for device ${deviceId} not found`);
                return;
            }

            const videoElement = videoCell.querySelector('video');
            if (!videoElement) {
                console.warn(`❌ Video element for device ${deviceId} not found`);
                return;
            }
            
            console.log(`✅ Found video element:`, {
                id: videoElement.id,
                hasAutoplay: videoElement.hasAttribute('autoplay'),
                hasMuted: videoElement.hasAttribute('muted'),
                hasPlaysinline: videoElement.hasAttribute('playsinline')
            });

            // Create WebRTC client if not already exists
            if (!this.webrtcClients.has(deviceId)) {
                console.log(`📡 Creating new WebRTC client for ${deviceId}`);
                const client = new WebRTCClient(
                    deviceId,
                    videoElement,
                    window.socket,
                    this.updateVideoStatus.bind(this, deviceId)
                );
                
                this.webrtcClients.set(deviceId, client);
                
                // Start connection
                console.log(`▶️ Starting WebRTC connection for ${deviceId}`);
                await client.start();
                console.log(`✅ WebRTC client started for ${deviceId}`);
            } else {
                console.log(`ℹ️ WebRTC client already exists for ${deviceId}`);
            }
        } catch (error) {
            console.error(`❌ Error initializing WebRTC client for ${deviceId}:`, error);
        }
    }

    updateVideoStatus(deviceId, status) {
        const cell = document.querySelector(`[data-drone="${deviceId}"]`);
        if (!cell) {
            console.warn(`Video cell for device ${deviceId} not found`);
            return;
        }

        const qualityElement = cell.querySelector('[id^="connectionQuality"]');
        if (!qualityElement) {
            console.warn(`Connection quality element for device ${deviceId} not found`);
            return;
        }

        switch (status) {
            case 'connected':
                qualityElement.textContent = 'Excellent';
                break;
            case 'reconnecting':
                qualityElement.textContent = 'Poor';
                break;
            case 'disconnected':
                qualityElement.textContent = 'Offline';
                break;
            default:
                qualityElement.textContent = status;
                break;
        }
    }

    getActiveVideoElement() {
        // Get the currently active video element
        const activeCell = this.grid.querySelector('.video-cell.active');
        if (activeCell) {
            return activeCell.querySelector('video');
        }
        
        // If no active cell, get the first video element
        const firstCell = this.grid.querySelector('.video-cell');
        if (firstCell) {
            return firstCell.querySelector('video');
        }
        
        return null;
    }

    // Clean up function to be called when the page is unloaded
    cleanup() {
        for (const client of this.webrtcClients.values()) {
            client.stop();
        }
        this.webrtcClients.clear();
    }
}

// Initialize the layout manager when the page loads
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('videoContainer')) {
        window.videoLayoutManager = new VideoLayoutManager();
    }
});

// Clean up when the page unloads
window.addEventListener('beforeunload', () => {
    if (window.videoLayoutManager) {
        window.videoLayoutManager.cleanup();
    }
});