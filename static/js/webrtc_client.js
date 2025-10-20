/**
 * WebRTC Client cho Sky WebApp
 * Xử lý kết nối WebRTC giữa client và Raspberry Pi
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
        
        // Thiết lập các event handlers cho socket
        this.setupSocketHandlers();
    }
    
    /**
     * Thiết lập các event handlers cho socket
     */
    setupSocketHandlers() {
        // Xử lý khi nhận được answer từ server
        this.socket.on('webrtc_answer', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                const remoteDesc = new RTCSessionDescription({
                    sdp: data.sdp,
                    type: data.type
                });
                
                await this.peerConnection.setRemoteDescription(remoteDesc);
                this.statusCallback('answer_received');
                
                // Thêm các ICE candidates đã lưu trữ
                this.addStoredIceCandidates();
            } catch (error) {
                console.error('Lỗi khi xử lý answer:', error);
                this.statusCallback('error', error.message);
            }
        });
        
        // Xử lý khi nhận được ICE candidate từ server
        this.socket.on('webrtc_ice_candidate', async (data) => {
            if (data.device_id !== this.deviceId) return;
            
            try {
                if (this.peerConnection && this.peerConnection.remoteDescription) {
                    await this.peerConnection.addIceCandidate(data.candidate);
                } else {
                    // Lưu trữ ICE candidate để thêm sau
                    this.iceCandidates.push(data.candidate);
                }
            } catch (error) {
                console.error('Lỗi khi xử lý ICE candidate:', error);
            }
        });
    }
    
    /**
     * Thêm các ICE candidates đã lưu trữ vào peer connection
     */
    async addStoredIceCandidates() {
        if (this.peerConnection && this.peerConnection.remoteDescription) {
            for (const candidate of this.iceCandidates) {
                try {
                    await this.peerConnection.addIceCandidate(candidate);
                } catch (error) {
                    console.error('Lỗi khi thêm ICE candidate đã lưu trữ:', error);
                }
            }
            this.iceCandidates = [];
        }
    }
    
    /**
     * Bắt đầu kết nối WebRTC
     */
    async start() {
        try {
            this.statusCallback('connecting');
            this.startTime = Date.now();
            
            // Tạo peer connection
            const configuration = {
                iceServers: [
                    { urls: 'stun:stun.l.google.com:19302' },
                    { urls: 'stun:stun1.l.google.com:19302' }
                ]
            };
            
            this.peerConnection = new RTCPeerConnection(configuration);
            
            // Xử lý khi trạng thái kết nối thay đổi
            this.peerConnection.onconnectionstatechange = () => {
                this.statusCallback('connection_state_change', this.peerConnection.connectionState);
                
                if (this.peerConnection.connectionState === 'connected') {
                    this.isConnected = true;
                    const latency = Date.now() - this.startTime;
                    this.statusCallback('connected', { latency });
                } else if (this.peerConnection.connectionState === 'failed' || 
                           this.peerConnection.connectionState === 'disconnected' ||
                           this.peerConnection.connectionState === 'closed') {
                    this.isConnected = false;
                    this.statusCallback('disconnected');
                }
            };
            
            // Xử lý khi nhận được ICE candidate
            this.peerConnection.onicecandidate = event => {
                if (event.candidate) {
                    this.socket.emit('webrtc_ice_candidate', {
                        device_id: this.deviceId,
                        candidate: event.candidate
                    });
                }
            };
            
            // Xử lý khi nhận được track
            this.peerConnection.ontrack = event => {
                this.videoElement.srcObject = event.streams[0];
                this.statusCallback('track_received', event.streams[0]);
                
                // Đánh giá chất lượng video
                const videoTrack = event.streams[0].getVideoTracks()[0];
                if (videoTrack) {
                    const settings = videoTrack.getSettings();
                    this.statusCallback('video_settings', settings);
                }
            };
            
            // Tạo offer
            const offer = await this.peerConnection.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: true
            });
            await this.peerConnection.setLocalDescription(offer);
            
            // Gửi offer đến server
            this.socket.emit('webrtc_offer', {
                device_id: this.deviceId,
                sdp: this.peerConnection.localDescription.sdp,
                type: this.peerConnection.localDescription.type
            });
            
            this.statusCallback('offer_sent');
        } catch (error) {
            console.error('Lỗi khi khởi tạo WebRTC:', error);
            this.statusCallback('error', error.message);
        }
    }
    
    /**
     * Dừng kết nối WebRTC
     */
    stop() {
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
        this.statusCallback('stopped');
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
}