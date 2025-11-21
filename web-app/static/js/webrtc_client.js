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
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được offer từ drone qua server
        this.socket.on('webrtc_offer', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                console.log('📥 Nhận WebRTC offer từ drone');
                this.statusCallback('offer_received');
                
                // If we're already confirmed connected, ignore duplicate offers
                if (this.connectedConfirmed) {
                    console.debug('Already connected; ignoring duplicate offer');
                    return;
                }
                
                // If we have a peer connection, check its state
                if (this.peerConnection) {
                    const state = this.peerConnection.signalingState;
                    // If we're in stable state, we can accept a new offer
                    // If we're in have-remote-offer, we can also accept (will replace)
                    // Otherwise, close and recreate
                    if (state !== 'stable' && state !== 'have-remote-offer') {
                        console.warn('Signaling state not ready for offer:', state, '- closing and recreating');
                        this.peerConnection.close();
                        this.peerConnection = null;
                    }
                }
                
                // Create peer connection if needed
                if (!this.peerConnection || this.peerConnection.connectionState === 'closed') {
                    await this.createPeerConnection();
                }
                
                // Set remote description (the offer from drone)
                const remoteDesc = new RTCSessionDescription({
                    sdp: data.sdp,
                    type: data.type
                });
                
                await this.peerConnection.setRemoteDescription(remoteDesc);
                console.log('✅ Đã thiết lập remote description từ offer');
                
                // Add any buffered ICE candidates
                await this.addStoredIceCandidates();
                
                // Create and send answer
                const answer = await this.peerConnection.createAnswer();
                await this.peerConnection.setLocalDescription(answer);
                
                // Send answer back to drone via server
                this.socket.emit('webrtc_answer', {
                    device_id: this.deviceId,
                    sdp: this.peerConnection.localDescription.sdp,
                    type: this.peerConnection.localDescription.type
                });
                
                console.log('📤 Đã gửi WebRTC answer đến drone');
                this.statusCallback('answer_sent');
                
                // Set connection timeout
                this.setConnectionTimeout();
            } catch (error) {
                console.error('❌ Lỗi khi xử lý offer:', error);
                this.statusCallback('error', error.message);
                this.handleConnectionFailure();
            }
        });
        
        // Xử lý khi nhận được ICE candidate từ drone qua server
        this.socket.on('webrtc_ice_candidate', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                const candidate = data.candidate;
                
                if (!candidate) {
                    console.debug('Received empty ICE candidate (end-of-candidates)');
                    return;
                }
                
                // Check if we can add the candidate now
                if (this.peerConnection && this.peerConnection.remoteDescription) {
                    try {
                        await this.peerConnection.addIceCandidate(candidate);
                        console.log('✅ Đã thêm ICE candidate');
                    } catch (error) {
                        console.warn('Failed to add ICE candidate:', error);
                        // Buffer it anyway
                        this.iceCandidates.push(candidate);
                    }
                } else {
                    // Buffer ICE candidate to add after setting remote description
                    this.iceCandidates.push(candidate);
                    console.log('💾 Đã lưu ICE candidate (remote description chưa sẵn sàng)');
                }
            } catch (error) {
                console.error('❌ Lỗi khi xử lý ICE candidate:', error);
            }
        });
    }
    
    /**
     * Thêm các ICE candidates đã lưu trữ vào peer connection
     */
    async addStoredIceCandidates() {
        if (this.peerConnection && this.peerConnection.remoteDescription && this.iceCandidates.length > 0) {
            console.log(`📦 Adding ${this.iceCandidates.length} buffered ICE candidates`);
            let successCount = 0;
            let failCount = 0;
            
            for (const candidate of this.iceCandidates) {
                try {
                    await this.peerConnection.addIceCandidate(candidate);
                    successCount++;
                } catch (error) {
                    console.warn('Failed to add buffered ICE candidate:', error);
                    failCount++;
                }
            }
            
            console.log(`✅ Added ${successCount}/${this.iceCandidates.length} buffered ICE candidates (${failCount} failed)`);
            this.iceCandidates = [];
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
                console.log('📹 Đã nhận video track từ drone');
                
                // Ensure the element is muted to allow autoplay
                this.videoElement.muted = true;
                this.videoElement.setAttribute('muted', '');
                this.videoElement.setAttribute('autoplay', '');
                this.videoElement.setAttribute('playsinline', '');
                
                // Set the stream
                this.videoElement.srcObject = event.streams[0];
                
                // Log track info
                const tracks = event.streams[0].getVideoTracks();
                console.log(`📊 Video tracks: ${tracks.length}`);
                tracks.forEach((t, i) => {
                    console.log(`  Track ${i}: ${t.kind} (id: ${t.id}, enabled: ${t.enabled})`);
                });
                
                // Handle video events
                this.videoElement.onloadedmetadata = () => {
                    console.log('📺 Video metadata loaded');
                    // Auto-play when metadata is ready
                    this.videoElement.play()
                        .then(() => console.log('▶️ Video playing successfully'))
                        .catch(e => console.warn('⚠️ Auto-play blocked:', e.message));
                };
                
                this.videoElement.onplaying = () => {
                    console.log('✅ Video element is now playing');
                    // Confirm connection when playback starts
                    this.connectedConfirmed = true;
                    this.isConnected = true;
                    this.reconnectAttempts = 0;
                    this.clearConnectionTimeout();
                    this.statusCallback('playing');
                };
                
                this.videoElement.onpause = () => {
                    console.log('⏸️ Video paused');
                };
                
                this.videoElement.onerror = (ev) => {
                    console.error('❌ Video element error:', ev);
                };
                
                this.statusCallback('track_received');
                this.isConnected = true;
                this.reconnectAttempts = 0;
            }
        };
        
        // Xử lý khi trạng thái kết nối thay đổi
        this.peerConnection.onconnectionstatechange = () => {
            const state = this.peerConnection.connectionState;
            console.log('🔄 Connection state:', state);
            
            if (state === 'connected') {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.connectedConfirmed = true;
                this.statusCallback('connected');
                this.clearConnectionTimeout();
                console.log('✅ WebRTC connection established');
            } else if (state === 'connecting') {
                console.log('🔗 WebRTC connecting...');
                this.statusCallback('connecting');
            } else if (state === 'disconnected') {
                console.warn('⚠️ WebRTC disconnected');
                this.isConnected = false;
                this.statusCallback('disconnected');
                // Wait a bit before trying to reconnect (might be temporary)
                setTimeout(() => {
                    if (this.peerConnection && this.peerConnection.connectionState === 'disconnected') {
                        console.log('🔄 Still disconnected, attempting recovery...');
                        this.handleConnectionFailure();
                    }
                }, 5000);
            } else if (state === 'failed') {
                console.error('❌ WebRTC connection failed');
                this.isConnected = false;
                this.statusCallback('connection_failed');
                this.handleConnectionFailure();
            } else if (state === 'closed') {
                console.log('🔒 WebRTC connection closed');
                this.isConnected = false;
                this.statusCallback('closed');
            }
        };
        
        // Xử lý khi ICE connection state thay đổi
        this.peerConnection.oniceconnectionstatechange = () => {
            const state = this.peerConnection.iceConnectionState;
            console.log('🧊 ICE connection state:', state);
            
            if (state === 'connected' || state === 'completed') {
                console.log('✅ ICE connection established');
            } else if (state === 'checking') {
                console.log('🔍 ICE connectivity checks in progress...');
            } else if (state === 'disconnected') {
                console.warn('⚠️ ICE connection disconnected');
                // Wait before reconnecting (might recover)
                setTimeout(() => {
                    if (this.peerConnection && this.peerConnection.iceConnectionState === 'disconnected') {
                        console.log('🔄 ICE still disconnected after 5s, attempting recovery...');
                        this.handleConnectionFailure();
                    }
                }, 5000);
            } else if (state === 'failed') {
                console.error('❌ ICE connection failed');
                this.handleConnectionFailure();
            }
        };
        
        // Xử lý khi ICE gathering state thay đổi
        this.peerConnection.onicegatheringstatechange = () => {
            console.log('ICE gathering state:', this.peerConnection.iceGatheringState);
        };
        
        // Xử lý khi tạo ICE candidate
        this.peerConnection.onicecandidate = (event) => {
            if (event.candidate) {
                // Gửi ICE candidate đến server để chuyển đến drone
                this.socket.emit('webrtc_ice_candidate', {
                    device_id: this.deviceId,
                    candidate: event.candidate
                });
                console.log('Đã gửi ICE candidate đến drone');
            }
        };
    }
    
    /**
     * Khởi tạo kết nối WebRTC
     */
    async start() {
        try {
            // Reset confirmation and guard against concurrent starts
            this.connectedConfirmed = false;
            if (this.starting) {
                console.debug('Start already in progress, skipping duplicate start');
                return;
            }
            this.starting = true;

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
            
            console.log('Đã gửi yêu cầu bắt đầu WebRTC đến drone');
            this.startTime = new Date();
            this.statusCallback('start_request_sent');
            
            // Thiết lập timeout cho kết nối; increment attempt id to identify this run
            this.connectionAttempt += 1;
            this.currentAttempt = this.connectionAttempt;
            this.setConnectionTimeout(this.currentAttempt);
            this.starting = false;
        } catch (error) {
            console.error('Lỗi khi khởi tạo kết nối WebRTC:', error);
            this.statusCallback('error', error.message);
            this.handleConnectionFailure();
            this.starting = false;
        }
    }
    
    /**
     * Dừng kết nối WebRTC
     */
    stop() {
        this.clearConnectionTimeout();
        
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
        this.statusCallback('stopped');
        console.log('Đã dừng kết nối WebRTC');
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
            console.debug('✅ Connection already active/confirmed; skipping connection timeout');
            return;
        }

        // Save the timer id and log for debugging races
        const attemptId = this.currentAttempt;
        const timerId = setTimeout(() => {
            // If this attempt has already been confirmed, skip
            if (this.currentAttempt !== attemptId || this.connectedConfirmed) {
                console.debug('⏭️ Timeout fired for stale attempt or already confirmed; skipping');
                return;
            }
            console.warn('⏱️ Kết nối WebRTC timeout sau', this.connectionTimeout / 1000, 'giây');
            this.statusCallback('connection_timeout');
            this.handleConnectionFailure();
        }, this.connectionTimeout);
        this.connectionTimer = timerId;
        console.debug('⏱️ Connection timeout set:', this.connectionTimeout / 1000, 'seconds');
    }
    
    /**
     * Xóa timeout cho kết nối
     */
    clearConnectionTimeout() {
        if (this.connectionTimer) {
            console.debug('⏹️ Clearing connection timeout');
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
            console.debug('Connection already confirmed; skipping reconnection');
            return;
        }

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Thử kết nối lại lần ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            this.statusCallback('reconnecting', { attempt: this.reconnectAttempts, max: this.maxReconnectAttempts });
            
            // Thử kết nối lại sau một khoảng delay để tránh race giữa timers và ontrack
            setTimeout(() => {
                try {
                    this.start();
                } catch (e) {
                    console.error('Lỗi khi thử start lại:', e);
                }
            }, this.reconnectDelay);
        } else {
            console.error('Đã vượt quá số lần thử kết nối lại tối đa');
            this.statusCallback('reconnect_failed');
            
            // Dừng kết nối
            this.stop();
        }
    }
}