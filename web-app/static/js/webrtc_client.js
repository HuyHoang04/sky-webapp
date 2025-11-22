/**
 * WebRTC Client cho Sky WebApp
 * Xử lý kết nối WebRTC giữa client và drone
 */

class WebRTCClient {
    constructor(deviceId, videoElement, socketIo, statusCallback) {
        this.deviceId = deviceId;
        this.videoElement = videoElement;
        this.socket = socketIo;
        this.statusCallback = statusCallback || function() {};
        this.peerConnection = null;
        this.startTime = null;
        this.iceCandidates = [];
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 2000; // ms
        this.connectionTimeout = 15000; // ms
        this.connectionTimer = null;
        this.connectedConfirmed = false;
        // connection attempt counter helps avoid stale timers from previous starts
        this.connectionAttempt = 0;
        this.currentAttempt = null;
        
        // 🔒 PRIORITY LOCK: Đảm bảo chỉ có 1 luồng xử lý RTC tại một thời điểm
        this.rtcLock = false;
        this.reconnecting = false;
        this.lastStateChange = Date.now();
        
        // 💓 ICE KEEPALIVE: Duy trì connection ổn định
        this.keepaliveInterval = null;
        this.keepaliveIntervalMs = 5000; // Ping every 5 seconds
        this.statsCheckInterval = null;
        this.statsCheckIntervalMs = 10000; // Check stats every 10 seconds
        this.lastBytesReceived = 0;
        this.lastPacketsReceived = 0;
        this.connectionStaleTimeout = 30000; // 30s without data = stale
        this.lastDataReceivedTime = Date.now();
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
        
        this._log('INFO', '🚀 WebRTC Client initialized', {
            deviceId: this.deviceId,
            maxReconnectAttempts: this.maxReconnectAttempts,
            connectionTimeout: this.connectionTimeout,
            keepaliveInterval: this.keepaliveIntervalMs,
            statsCheckInterval: this.statsCheckIntervalMs
        });
    }
    
    /**
     * Logger với timestamp và priority tracking
     */
    _log(level, message, data = {}) {
        const timestamp = new Date().toISOString();
        const prefix = `[WebRTC:${this.deviceId}]`;
        const logData = {
            timestamp,
            attempt: this.currentAttempt,
            reconnectAttempts: this.reconnectAttempts,
            locked: this.rtcLock,
            reconnecting: this.reconnecting,
            confirmed: this.connectedConfirmed,
            ...data
        };
        
        const logMsg = `${prefix} [${level}] ${message}`;
        
        if (level === 'ERROR') {
            console.error(logMsg, logData);
        } else if (level === 'WARN') {
            console.warn(logMsg, logData);
        } else {
            console.log(logMsg, logData);
        }
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được offer từ drone qua server
        this.socket.on('webrtc_offer', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            // 🔒 PRIORITY CHECK: Nếu đang reconnect hoặc locked, chờ
            if (this.rtcLock) {
                this._log('WARN', '🔒 RTC locked, queuing offer', { state: 'locked' });
                await this._waitForUnlock(5000); // Chờ max 5s
            }
            
            this.rtcLock = true; // Lock để tránh tranh chấp
            
            try {
                this._log('INFO', '📩 Received WebRTC offer from drone', {
                    offerType: data.type,
                    sdpLength: data.sdp?.length
                });
                this.statusCallback('offer_received');
                // If we're already confirmed connected, ignore duplicate offers
                if (this.connectedConfirmed && this.peerConnection?.connectionState === 'connected') {
                    this._log('INFO', '✅ Already connected, ignoring duplicate offer', {
                        connectionState: this.peerConnection?.connectionState
                    });
                    this.rtcLock = false; // Unlock
                    return;
                }
                // If signaling state is not stable, reset to avoid "Called in wrong state: stable" errors
                if (this.peerConnection && this.peerConnection.signalingState && this.peerConnection.signalingState !== 'stable') {
                    this._log('WARN', '⚠️ Signaling state not stable, resetting peer connection', {
                        signalingState: this.peerConnection.signalingState,
                        connectionState: this.peerConnection.connectionState
                    });
                    try {
                        this.stop();
                    } catch (e) {
                        this._log('ERROR', 'Error stopping peerConnection during offer handling', { error: e.message });
                    }
                    await this.createPeerConnection();
                }
                
                // Đảm bảo peer connection đã được khởi tạo
                if (!this.peerConnection || this.peerConnection.connectionState === 'closed') {
                    await this.createPeerConnection();
                }
                
                // Nhận offer từ drone và tạo answer
                const remoteDesc = new RTCSessionDescription({
                    sdp: data.sdp,
                    type: data.type
                });
                
                await this.peerConnection.setRemoteDescription(remoteDesc);
                this._log('INFO', '✅ Set remote description from offer');
                
                // Thêm các ICE candidates đã lưu trữ (nếu có)
                const addedCandidates = await this.addStoredIceCandidates();
                if (addedCandidates > 0) {
                    this._log('INFO', `📌 Added ${addedCandidates} stored ICE candidates`);
                }
                
                // Tạo answer
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                
                // Gửi answer về server để chuyển đến drone
                this.socket.emit('webrtc_answer', {
                    device_id: this.deviceId,
                    sdp: this.peerConnection.localDescription.sdp,
                    type: this.peerConnection.localDescription.type
                });
                
                this._log('INFO', '📤 Sent WebRTC answer to drone', {
                    answerType: this.peerConnection.localDescription.type
                });
                this.statusCallback('answer_sent');
                
                // Thiết lập timeout cho kết nối
                this.setConnectionTimeout();
            } catch (error) {
                this._log('ERROR', '❌ Error handling offer', {
                    error: error.message,
                    stack: error.stack
                });
                this.statusCallback('error', error.message);
                this.handleConnectionFailure();
            } finally {
                this.rtcLock = false; // ✅ Always unlock
                this._log('INFO', '🔓 RTC unlocked after offer processing');
            }
        });
        
        // Xử lý khi nhận được ICE candidate từ drone qua server
        this.socket.on('webrtc_ice_candidate', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                const candidateStr = data.candidate?.candidate?.substring(0, 50) || 'N/A';
                
                if (this.peerConnection && this.peerConnection.remoteDescription) {
                    await this.peerConnection.addIceCandidate(data.candidate);
                    this._log('INFO', '🧊 Added ICE candidate', {
                        candidate: candidateStr,
                        iceConnectionState: this.peerConnection.iceConnectionState
                    });
                } else {
                    // Lưu trữ ICE candidate để thêm sau
                    this.iceCandidates.push(data.candidate);
                    this._log('INFO', '💾 Stored ICE candidate for later', {
                        candidate: candidateStr,
                        queueSize: this.iceCandidates.length
                    });
                }
            } catch (error) {
                this._log('ERROR', '❌ Error handling ICE candidate', {
                    error: error.message
                });
            }
        });
    }
    
    /**
     * Thêm các ICE candidates đã lưu trữ vào peer connection
     */
    async addStoredIceCandidates() {
        let addedCount = 0;
        if (this.peerConnection && this.peerConnection.remoteDescription) {
            for (const candidate of this.iceCandidates) {
                try {
                    await this.peerConnection.addIceCandidate(candidate);
                    addedCount++;
                } catch (error) {
                    this._log('ERROR', 'Failed to add stored ICE candidate', {
                        error: error.message
                    });
                }
            }
            this.iceCandidates = [];
        }
        return addedCount;
    }
    
    /**
     * Chờ RTC unlock với timeout
     */
    async _waitForUnlock(timeout = 5000) {
        const startTime = Date.now();
        while (this.rtcLock && (Date.now() - startTime) < timeout) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        if (this.rtcLock) {
            this._log('WARN', '⏱️ Wait for unlock timed out', { timeout });
        }
    }
    
    /**
     * Tạo peer connection mới
     */
    async createPeerConnection() {
        // Tạo peer connection với nhiều STUN servers để tăng khả năng kết nối
        this.peerConnection = new RTCPeerConnection({
            iceServers: [
                {'urls': 'stun:stun.l.google.com:19302'}, 
                {'urls': 'turn:relay1.expressturn.com:3480', 'username': '000000002076929768', 'credential': 'glxmCqGZVm2WqKrB/EXZsf2SZGc='}  
            ],
            iceCandidatePoolSize: 10,
            bundlePolicy: 'max-bundle',
            rtcpMuxPolicy: 'require'
        });
        
        // Thiết lập các event handlers cho peer connection
        this.setupPeerConnectionHandlers();
        console.log('Đã tạo peer connection mới');
        return this.peerConnection;
    }
    
    /**
     * Thiết lập các event handlers cho peer connection
     */
    setupPeerConnectionHandlers() {
        // Xử lý khi nhận được track từ drone
        this.peerConnection.ontrack = (event) => {
            if (event.streams && event.streams[0]) {
                console.log('Đã nhận video track từ drone');
                // Ensure the element is muted to allow autoplay in modern browsers
                try {
                    this.videoElement.muted = true;
                    this.videoElement.setAttribute('muted', '');
                } catch (e) {
                    // ignore
                }

                this.videoElement.srcObject = event.streams[0];

                // Debug: log track info
                try {
                    const tracks = event.streams[0].getVideoTracks();
                    console.log(`Stream video tracks count: ${tracks.length}`);
                    tracks.forEach((t, i) => console.log(`Track[${i}]: id=${t.id}, kind=${t.kind}`));
                } catch (e) {
                    console.debug('Could not enumerate tracks:', e);
                }

                // Attach playback event handlers for debugging
                this.videoElement.onplaying = () => {
                    console.log('Video element playing');
                    // Confirm connection only when playback truly starts
                    this.connectedConfirmed = true;
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    // Clear only the timer for this attempt
                    this.clearConnectionTimeout();
                };
                this.videoElement.onpause = () => console.log('Video element paused');
                this.videoElement.onerror = (ev) => console.error('Video element error', ev);

                // Try to play when metadata is loaded; set muted before play to avoid NotAllowedError
                this.videoElement.onloadedmetadata = () => {
                    // Some browsers still block autoplay; ensure we try to play but catch errors
                    this.videoElement.play().then(() => {
                        console.log('play() succeeded');
                    }).catch(e => {
                        console.warn('Không thể tự động phát video:', e);
                    });
                };

                // Make video element visually obvious during debugging
                try {
                    this.videoElement.style.border = '2px solid lime';
                } catch (e) {}
                
                this.statusCallback('track_received');
                
                // Note: final confirmation and clearing of timeout happens in onplaying handler
                // Keep basic state updated here
                this.isConnected = true;
                this.reconnectAttempts = 0;
            }
        };
        
        // Xử lý khi trạng thái kết nối thay đổi
        this.peerConnection.onconnectionstatechange = () => {
            const state = this.peerConnection.connectionState;
            const timeSinceLastChange = Date.now() - this.lastStateChange;
            this.lastStateChange = Date.now();
            
            this._log('INFO', `🔄 RTC Connection State: ${state}`, {
                previousState: this.isConnected ? 'connected' : 'disconnected',
                timeSinceLastChange: `${timeSinceLastChange}ms`,
                iceConnectionState: this.peerConnection.iceConnectionState,
                signalingState: this.peerConnection.signalingState
            });
            
            if (state === 'connected') {
                this.isConnected = true;
                this.reconnectAttempts = 0; // Reset số lần thử kết nối lại
                this.reconnecting = false;
                this.statusCallback('connected');
                // Mark confirmed when PC reaches connected as a stronger signal
                this.connectedConfirmed = true;
                this._log('INFO', '✅ RTC Connection established successfully', {
                    attempt: this.currentAttempt
                });
                this.clearConnectionTimeout();
                // 💓 Start keepalive when connected
                this.startKeepalive();
            } else if (state === 'disconnected') {
                this.isConnected = false;
                this.statusCallback('disconnected');
                this._log('WARN', '⚠️ RTC Connection disconnected, will retry', {
                    reconnecting: this.reconnecting
                });
                // 💓 Stop keepalive when disconnected
                this.stopKeepalive();
                // Thử kết nối lại sau một khoảng thời gian (nếu chưa đang reconnect)
                if (!this.reconnecting) {
                    setTimeout(() => this.handleConnectionFailure(), this.reconnectDelay);
                }
            } else if (state === 'failed' || state === 'closed') {
                this.isConnected = false;
                this.statusCallback('connection_failed');
                this._log('ERROR', `❌ RTC Connection ${state}`, {
                    reconnecting: this.reconnecting
                });
                // 💓 Stop keepalive when failed/closed
                this.stopKeepalive();
                if (!this.reconnecting) {
                    this.handleConnectionFailure();
                }
            }
        };
        
        // Xử lý khi ICE connection state thay đổi
        this.peerConnection.oniceconnectionstatechange = () => {
            const iceState = this.peerConnection.iceConnectionState;
            const rtcState = this.peerConnection.connectionState;
            
            this._log('INFO', `🧊 ICE Connection State: ${iceState}`, {
                rtcConnectionState: rtcState,
                reconnecting: this.reconnecting,
                confirmed: this.connectedConfirmed
            });
            
            if (iceState === 'connected' || iceState === 'completed') {
                this._log('INFO', '✅ ICE Connection established', { state: iceState });
            } else if (iceState === 'checking') {
                this._log('INFO', '🔍 ICE checking candidates...');
            } else if (iceState === 'disconnected') {
                this._log('WARN', '⚠️ ICE disconnected', {
                    willReconnect: !this.reconnecting
                });
                // Chỉ trigger reconnect nếu chưa đang reconnect
                if (!this.reconnecting) {
                    setTimeout(() => this.handleConnectionFailure(), this.reconnectDelay);
                }
            } else if (iceState === 'failed') {
                this._log('ERROR', '❌ ICE connection failed', {
                    willReconnect: !this.reconnecting
                });
                // Thử kết nối lại nếu ICE connection thất bại
                if (!this.reconnecting) {
                    setTimeout(() => this.handleConnectionFailure(), this.reconnectDelay);
                }
            }
        };
        
        // Xử lý khi ICE gathering state thay đổi
        this.peerConnection.onicegatheringstatechange = () => {
            const gatheringState = this.peerConnection.iceGatheringState;
            this._log('INFO', `🔎 ICE Gathering State: ${gatheringState}`);
        };
        
        // Xử lý khi tạo ICE candidate
        this.peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                const candidateStr = event.candidate.candidate.substring(0, 50);
                // Gửi ICE candidate đến server để chuyển đến drone
                this.socket.emit('webrtc_ice_candidate', {
                    device_id: this.deviceId,
                    candidate: event.candidate
                });
                this._log('INFO', '📤 Sent ICE candidate to drone', {
                    candidate: candidateStr,
                    type: event.candidate.type,
                    protocol: event.candidate.protocol
                });
            } else {
                this._log('INFO', '✅ ICE gathering complete (null candidate)');
            }
        };
    }
    
    /**
     * Khởi tạo kết nối WebRTC
     */
    async start() {
        // 🔒 PRIORITY: Chờ nếu đang locked
        if (this.rtcLock) {
            this._log('WARN', '🔒 RTC locked, waiting before start');
            await this._waitForUnlock(3000);
        }
        
        try {
            // Reset confirmation and guard against concurrent starts
            this.connectedConfirmed = false;
            if (this.starting) {
                this._log('WARN', '⚠️ Start already in progress, skipping duplicate');
                return;
            }
            this.starting = true;
            this._log('INFO', '🚀 Starting WebRTC connection...');

            // Đóng kết nối cũ nếu có
            if (this.peerConnection) {
                await this.stop();
            }
            
            // Tạo peer connection mới
            await this.createPeerConnection();
            
            // Gửi yêu cầu bắt đầu đến drone (drone sẽ là offerer)
            this.socket.emit('start_webrtc', {
                device_id: this.deviceId
            });
            
            this.startTime = new Date();
            this._log('INFO', '📤 Sent start_webrtc request to drone', {
                timestamp: this.startTime.toISOString()
            });
            this.statusCallback('start_request_sent');
            
            // Thiết lập timeout cho kết nối; increment attempt id to identify this run
            this.connectionAttempt += 1;
            this.currentAttempt = this.connectionAttempt;
            this.setConnectionTimeout(this.currentAttempt);
            this.starting = false;
        } catch (error) {
            this._log('ERROR', '❌ Error starting WebRTC connection', {
                error: error.message,
                stack: error.stack
            });
            this.statusCallback('error', error.message);
            this.handleConnectionFailure();
            this.starting = false;
        }
    }
    
    /**
     * Dừng kết nối WebRTC
     */
    stop() {
        this._log('INFO', '🛑 Stopping WebRTC connection');
        this.clearConnectionTimeout();
        this.stopKeepalive(); // 💓 Stop keepalive
        
        if (this.peerConnection) {
            this.peerConnection.close();
            this.peerConnection = null;
        }
        
        if (this.videoElement.srcObject) {
            const tracks = this.videoElement.srcObject.getTracks();
            tracks.forEach(track => track.stop());
            this.videoElement.srcObject = null;
        }
        
        this.isConnected = false;
        this.connectedConfirmed = false;
        this.starting = false;
        this.reconnecting = false; // Reset reconnecting flag
        this.rtcLock = false; // Unlock
        this.statusCallback('stopped');
        this._log('INFO', '✅ WebRTC connection stopped and cleaned up');
    }
    
    /**
     * Kiểm tra xem kết nối có đang hoạt động không
     */
    isActive() {
        return this.isConnected;
    }
    
    /**
     * Lấy thông tin thống kê về kết nối
     */
    async getStats() {
        if (!this.peerConnection) {
            return null;
        }
        
        try {
            const stats = await this.peerConnection.getStats();
            return stats;
        } catch (error) {
            console.error('Lỗi khi lấy thống kê:', error);
            return null;
        }
    }
    
    /**
     * Thiết lập timeout cho kết nối
     */
    setConnectionTimeout() {
        // Always clear any previous timer first
        this.clearConnectionTimeout();

        // If already confirmed connected, don't set a timeout
        if (this.connectedConfirmed || (this.peerConnection && this.peerConnection.connectionState === 'connected')) {
            console.debug('Connection already active/confirmed; skipping connection timeout');
            return;
        }

        // If the video element is already playing, skip creating a timeout (avoid false positives)
        try {
            if (this.videoElement && !this.videoElement.paused && this.videoElement.readyState >= 3) {
                console.debug('Video element already playing; skipping connection timeout');
                return;
            }
        } catch (e) {
            // ignore cross-origin or other errors when checking element state
        }

        // Save the timer id and log for debugging races. Capture attempt id to avoid clearing someone else's timer.
        const attemptId = this.currentAttempt;
        const timerId = setTimeout(() => {
            // If this attempt has already been confirmed, skip
            if (this.currentAttempt !== attemptId || this.connectedConfirmed) {
                console.debug('Timeout fired for stale attempt or already confirmed; skipping', {attemptId, currentAttempt: this.currentAttempt, connectedConfirmed: this.connectedConfirmed});
                return;
            }
            console.warn('Kết nối WebRTC timeout sau', this.connectionTimeout, 'ms', 'attemptId:', attemptId);
            this.statusCallback('connection_timeout');
            this.handleConnectionFailure();
        }, this.connectionTimeout);
        this.connectionTimer = timerId;
        console.debug('Connection timeout set (ms):', this.connectionTimeout, 'timerId:', this.connectionTimer, 'attemptId:', attemptId);
    }
    
    /**
     * Xóa timeout cho kết nối
     */
    clearConnectionTimeout() {
        if (this.connectionTimer) {
            console.debug('Clearing connection timeout, timerId:', this.connectionTimer, 'connectedConfirmed:', this.connectedConfirmed, 'currentAttempt:', this.currentAttempt);
            clearTimeout(this.connectionTimer);
            this.connectionTimer = null;
        }
    }
    
    /**
     * Xử lý khi kết nối thất bại
     */
    handleConnectionFailure() {
        // If we're already confirmed connected, do not attempt recovery
        if (this.connectedConfirmed || (this.peerConnection && this.peerConnection.connectionState === 'connected')) {
            this._log('INFO', '✅ Connection already confirmed, skipping reconnection');
            return;
        }
        
        // 🔒 PRIORITY: Prevent concurrent reconnection attempts
        if (this.reconnecting) {
            this._log('WARN', '⚠️ Already reconnecting, skipping duplicate attempt');
            return;
        }

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.reconnecting = true; // 🔒 Set flag để tránh multiple reconnect
            
            this._log('INFO', `🔄 Attempting reconnection ${this.reconnectAttempts}/${this.maxReconnectAttempts}`, {
                delay: this.reconnectDelay,
                reason: 'connection_failure'
            });
            this.statusCallback('reconnecting', { attempt: this.reconnectAttempts, max: this.maxReconnectAttempts });
            
            // Thử kết nối lại sau một khoảng delay để tránh race giữa timers và ontrack
            setTimeout(() => {
                try {
                    this.start();
                    // Reset reconnecting flag sau khi start
                    setTimeout(() => {
                        this.reconnecting = false;
                    }, 1000); // Reset sau 1s để tránh immediate duplicate
                } catch (e) {
                    this._log('ERROR', '❌ Error during reconnection attempt', {
                        error: e.message
                    });
                    this.reconnecting = false;
                }
            }, this.reconnectDelay);
        } else {
            this._log('ERROR', '❌ Max reconnection attempts exceeded', {
                maxAttempts: this.maxReconnectAttempts
            });
            this.statusCallback('reconnect_failed');
            this.reconnecting = false;
            
            // Dừng kết nối
            this.stop();
        }
    }
    
    /**
     * 💓 Bắt đầu ICE keepalive để duy trì connection
     */
    startKeepalive() {
        // Clear existing intervals
        this.stopKeepalive();
        
        this._log('INFO', '💓 Starting ICE keepalive mechanism', {
            keepaliveInterval: this.keepaliveIntervalMs,
            statsCheckInterval: this.statsCheckIntervalMs
        });
        
        // Keepalive ping - gửi dummy data channel message để keep connection alive
        this.keepaliveInterval = setInterval(() => {
            if (!this.peerConnection || this.peerConnection.connectionState !== 'connected') {
                this._log('WARN', '💓 Keepalive stopped - connection not active');
                this.stopKeepalive();
                return;
            }
            
            // Check ICE connection state
            const iceState = this.peerConnection.iceConnectionState;
            if (iceState === 'disconnected' || iceState === 'failed') {
                this._log('WARN', '💓 Keepalive detected ICE issue', { iceState });
                return;
            }
            
            this._log('INFO', '💓 Keepalive ping', {
                iceState: iceState,
                connectionState: this.peerConnection.connectionState
            });
        }, this.keepaliveIntervalMs);
        
        // Stats monitoring - kiểm tra data flow
        this.statsCheckInterval = setInterval(async () => {
            if (!this.peerConnection || this.peerConnection.connectionState !== 'connected') {
                return;
            }
            
            try {
                const stats = await this.peerConnection.getStats();
                let bytesReceived = 0;
                let packetsReceived = 0;
                let packetsLost = 0;
                let jitter = 0;
                
                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && report.kind === 'video') {
                        bytesReceived += report.bytesReceived || 0;
                        packetsReceived += report.packetsReceived || 0;
                        packetsLost += report.packetsLost || 0;
                        jitter += report.jitter || 0;
                    }
                });
                
                // Check if data is flowing
                const bytesReceivedDelta = bytesReceived - this.lastBytesReceived;
                const packetsReceivedDelta = packetsReceived - this.lastPacketsReceived;
                
                if (bytesReceivedDelta > 0 || packetsReceivedDelta > 0) {
                    // Data is flowing - update timestamp
                    this.lastDataReceivedTime = Date.now();
                    this._log('INFO', '📊 Stats check - data flowing', {
                        bytesReceived: bytesReceivedDelta,
                        packetsReceived: packetsReceivedDelta,
                        packetsLost: packetsLost,
                        jitter: jitter.toFixed(3)
                    });
                } else {
                    // No data received - check if stale
                    const timeSinceLastData = Date.now() - this.lastDataReceivedTime;
                    this._log('WARN', '⚠️ Stats check - no new data', {
                        timeSinceLastData: `${timeSinceLastData}ms`,
                        threshold: `${this.connectionStaleTimeout}ms`
                    });
                    
                    // If no data for too long, consider connection stale
                    if (timeSinceLastData > this.connectionStaleTimeout) {
                        this._log('ERROR', '❌ Connection stale - no data received', {
                            timeSinceLastData: `${timeSinceLastData}ms`
                        });
                        // Trigger reconnection
                        if (!this.reconnecting) {
                            this.handleConnectionFailure();
                        }
                    }
                }
                
                // Update last values
                this.lastBytesReceived = bytesReceived;
                this.lastPacketsReceived = packetsReceived;
                
            } catch (error) {
                this._log('ERROR', '❌ Stats check failed', {
                    error: error.message
                });
            }
        }, this.statsCheckIntervalMs);
        
        // Reset data received time
        this.lastDataReceivedTime = Date.now();
        this.lastBytesReceived = 0;
        this.lastPacketsReceived = 0;
    }
    
    /**
     * 💓 Dừng ICE keepalive
     */
    stopKeepalive() {
        if (this.keepaliveInterval) {
            clearInterval(this.keepaliveInterval);
            this.keepaliveInterval = null;
            this._log('INFO', '💓 Keepalive stopped');
        }
        
        if (this.statsCheckInterval) {
            clearInterval(this.statsCheckInterval);
            this.statsCheckInterval = null;
            this._log('INFO', '📊 Stats monitoring stopped');
        }
    }
}