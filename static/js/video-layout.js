/**
 * Video Layout Manager for Sky WebApp
 * Handles switching between different video layout modes and managing multiple video streams
 */

class VideoLayoutManager {
    constructor() {
        this.container = document.getElementById('videoContainer');
        this.grid = document.getElementById('videoGrid');
        this.layoutSelect = document.getElementById('layoutSelect');
        this.webrtcClients = new Map(); // Map to store WebRTC clients for each video

        this.setupLayoutSwitcher();
        this.initializeWebRTCClients();
    }

    setupLayoutSwitcher() {
        if (this.layoutSelect) {
            this.layoutSelect.addEventListener('change', (event) => {
                const layout = event.target.value;
                this.switchLayout(layout);
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
            case 'drone1':
                this.container.classList.add('single-view');
                document.querySelector('[data-drone="drone1"]').classList.add('active');
                break;
            case 'drone2':
                this.container.classList.add('single-view');
                document.querySelector('[data-drone="drone2"]').classList.add('active');
                break;
            default: // single
                this.container.classList.add('single-view');
                document.querySelector('[data-drone="drone1"]').classList.add('active');
                break;
        }

        // Force video resize event
        window.dispatchEvent(new Event('resize'));
    }

    async initializeWebRTCClients() {
        // Initialize WebRTC client for drone 1
        const video1 = document.getElementById('videoStream1');
        if (video1) {
            this.webrtcClients.set('drone1', new WebRTCClient(
                'drone1',
                video1,
                window.socket,
                this.updateVideoStatus.bind(this, 'drone1')
            ));
        }

        // Initialize WebRTC client for drone 2
        const video2 = document.getElementById('videoStream2');
        if (video2) {
            this.webrtcClients.set('drone2', new WebRTCClient(
                'drone2',
                video2,
                window.socket,
                this.updateVideoStatus.bind(this, 'drone2')
            ));
        }

        // Start all video streams
        for (const client of this.webrtcClients.values()) {
            await client.start();
        }
    }

    updateVideoStatus(droneId, status) {
        const cell = document.querySelector(`[data-drone="${droneId}"]`);
        const quality = cell.querySelector(`#connectionQuality${droneId.slice(-1)}`);

        switch (status) {
            case 'connected':
                quality.textContent = 'Excellent';
                break;
            case 'reconnecting':
                quality.textContent = 'Poor';
                break;
            case 'disconnected':
                quality.textContent = 'Offline';
                break;
        }
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