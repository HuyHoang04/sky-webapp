# SkyAid Drone Surveillance System

A comprehensive real-time drone surveillance and flood rescue system built with Python, Flask, and modern web technologies. The system enables live video streaming, GPS tracking, object detection, and voice analysis for effective flood rescue operations.

## 🚀 Features

### Core Functionality
- **Real-time Video Streaming**: WebRTC-based low-latency video transmission from drones to web dashboard
- **GPS Tracking**: Live GPS data visualization on interactive maps with real-time updates
- **Object Detection**: AI-powered person detection using YOLOv11 models (earth vs sea classification)
- **Voice Analysis**: Speech-to-text transcription and intent analysis using Whisper and Phi-3 LLM
- **Multi-drone Support**: Scalable architecture supporting multiple concurrent drone connections
- **Responsive Dashboard**: Modern web interface with video grid, map integration, and real-time statistics

### Advanced Analytics
- **Image Analytics Server**: Dedicated service for computer vision processing with YOLO object detection
- **Voice Analytics Server**: Specialized service for audio transcription and natural language understanding
- **Cloud Storage**: Automatic image and audio upload to Cloudinary for archival and analysis
- **Real-time Notifications**: WebSocket-based instant alerts for detection events

### Technical Features
- **Microservices Architecture**: Modular design with separate services for different functionalities
- **WebRTC Signaling**: Robust peer-to-peer video communication with STUN/TURN server support
- **Socket.IO Integration**: Bidirectional real-time communication between clients and servers
- **Database Integration**: SQLite-based data persistence for GPS, detection, and mission data
- **RESTful APIs**: Well-documented endpoints for system integration

## 🏗️ Architecture

### System Overview
```
SkyAid System Architecture
├── Web Application (Flask + Socket.IO)
│   ├── Dashboard UI (HTML/CSS/JS)
│   ├── Video Management (WebRTC)
│   ├── GPS Visualization (Leaflet.js)
│   └── API Controllers
├── Drone Client (Python + aiortc)
│   ├── Video Streaming (WebRTC)
│   ├── GPS Transmission
│   └── Object Detection (YOLO)
├── Analytics Services
│   ├── Image Analytics (YOLOv11)
│   └── Voice Analytics (Whisper + Phi-3)
└── Supporting Systems
    ├── Record System (Audio Capture)
    └── Cloud Storage (Cloudinary)
```

### Detailed Project Structure
```
sky-webapp/
├── analytics-image-server/          # AI-powered image analysis service
│   ├── best.pt                      # YOLOv11 trained model weights
│   ├── main.py                      # Image detection server with YOLO inference
│   └── requirements.txt             # Python dependencies for image analytics
├── analytics-voice-server/          # Voice analysis and transcription service
│   ├── main.py                      # Whisper + Phi-3 voice processing server
│   └── requirements.txt             # Python dependencies for voice analytics
├── drone-app/                       # Drone client application
│   ├── camera_utils.py              # Camera capture and processing utilities
│   ├── gps_utils.py                 # GPS data acquisition and processing
│   ├── main.py                      # Main drone client with WebRTC streaming
│   ├── model_fp32.onnx              # FP32 ONNX model for object detection
│   ├── model_int8.onnx              # INT8 quantized ONNX model (optimized)
│   ├── nano_model_fp32.onnx         # Nano-optimized FP32 model
│   ├── video_stream.py              # WebRTC video streaming with object detection
│   ├── __init__.py                  # Package initialization
│   └── requirements.txt             # Python dependencies for drone client
├── record-system/                   # Audio recording and capture system
│   ├── main.py                      # Audio recording service
│   └── requirements.txt             # Python dependencies for audio recording
└── web-app/                         # Main web application (Flask)
    ├── app.py                       # Flask application entry point
    ├── controller/                  # MVC Controllers
    │   ├── capture_controller.py    # Image/video capture handling
    │   ├── detection_controller.py  # Object detection API endpoints
    │   ├── gps_controller.py        # GPS data management
    │   ├── main_controller.py       # Main application routes
    │   ├── mission_controller.py    # Mission planning and execution
    │   ├── video_controller.py      # Video streaming management
    │   └── voice_controller.py      # Voice analysis integration
    ├── database.py                  # Database connection and initialization
    ├── model/                       # Data models
    │   ├── capture_model.py         # Capture data models
    │   ├── gps_model.py             # GPS data structures
    │   ├── mission_model.py         # Mission planning models
    │   ├── video_model.py           # Video stream models
    │   └── voice_model.py           # Voice analysis models
    ├── requirements.txt             # Python dependencies
    ├── services/                    # Business logic services
    │   ├── mission_service.py       # Mission execution logic
    │   ├── route_optimizer.py       # Path optimization algorithms
    │   ├── voice_service.py         # Voice processing services
    │   └── __init__.py              # Services package init
    ├── socket_instance.py           # Socket.IO instance configuration
    ├── static/                      # Static assets
    │   ├── css/                     # Stylesheets
    │   │   ├── mission-tools.css    # Mission management UI styles
    │   │   ├── style.css            # Main application styles
    │   │   ├── video-grid.css       # Video grid layout styles
    │   │   └── voice.css            # Voice interface styles
    │   ├── images/                  # Static images
    │   │   ├── drone-bg.png         # Drone background image
    │   │   └── logo.png             # Application logo
    │   └── js/                      # Client-side JavaScript
    │       ├── gps_client.js        # GPS data visualization
    │       ├── main.js              # Main application logic
    │       ├── mission_management.js # Mission control interface
    │       ├── video-layout.js      # Video grid management
    │       ├── voice.js             # Voice interface handling
    │       └── webrtc_client.js     # WebRTC video client
    ├── tasks/                       # Background tasks
    │   └── voice_cleanup_task.py    # Voice data cleanup jobs
    └── templates/                   # Jinja2 HTML templates
        ├── dashboard.html           # Main dashboard interface
        ├── detection.html           # Object detection results page
        ├── index.html               # Landing page
        ├── layout.html              # Base template layout
        ├── mission.html             # Mission planning interface
        ├── voice.html               # Voice analysis interface
        └── webrtc.html              # WebRTC video streaming page
```

### Key Components

#### 🎥 Video Streaming Pipeline
- **WebRTC Implementation**: Peer-to-peer video streaming with STUN/TURN server support
- **Multi-format Support**: H.264/AVC encoding with adaptive bitrate
- **Real-time Processing**: Object detection overlay on live video streams
- **Multi-camera Layout**: Dynamic video grid with single/multi-view modes

#### 🛰️ GPS Tracking System
- **Real-time Updates**: Live GPS coordinate transmission via WebSocket
- **Map Integration**: Leaflet.js-powered interactive mapping
- **Multi-device Tracking**: Support for multiple drones and rescue devices
- **Historical Data**: GPS trail visualization and mission logging

#### 🤖 AI Analytics Pipeline
- **Object Detection**: YOLOv8 models for person detection (earth vs sea classification)
- **Voice Processing**: Whisper ASR + Phi-3 LLM for intent analysis
- **Real-time Inference**: Optimized models for edge computing on drones
- **Cloud Offloading**: Heavy processing moved to dedicated analytics servers

#### 📡 Communication Architecture
- **Socket.IO**: Bidirectional real-time communication
- **REST APIs**: Standard HTTP endpoints for data operations
- **Event-driven**: Asynchronous event handling for real-time updates
- **Scalable Design**: Microservices architecture for horizontal scaling

### Data Flow & Workflow

#### Video Streaming Workflow
1. **Drone Capture**: Camera captures video frames in real-time
2. **Local Processing**: YOLO inference for object detection on drone
3. **WebRTC Streaming**: Compressed video sent to web dashboard via WebRTC
4. **Server Processing**: Analytics server performs additional AI processing
5. **UI Display**: Video rendered in web interface with detection overlays

#### GPS Tracking Workflow
1. **GPS Acquisition**: Drone reads GPS coordinates from onboard module
2. **Data Transmission**: Coordinates sent via WebSocket to web server
3. **Database Storage**: GPS data persisted for historical analysis
4. **Map Visualization**: Real-time position updates on Leaflet map
5. **Mission Logging**: GPS trails recorded for mission debriefing

#### Voice Analysis Workflow
1. **Audio Capture**: Record system captures audio from rescue operations
2. **Cloud Upload**: Audio files uploaded to Cloudinary for storage
3. **Transcription**: Whisper model converts speech to text
4. **Intent Analysis**: Phi-3 LLM analyzes intent (injury, supplies needed, etc.)
5. **Alert Generation**: Critical intents trigger real-time notifications

#### Detection & Alert Workflow
1. **Real-time Detection**: YOLO processes video frames for person detection
2. **Classification**: Earth vs sea person classification
3. **Statistics Update**: Live counters updated on dashboard
4. **Alert Triggers**: Threshold-based notifications for rescue teams
5. **Data Archival**: Detection results stored for mission analysis

### Technical Specifications

#### Performance Characteristics
- **Video Latency**: <500ms end-to-end WebRTC streaming
- **Detection Accuracy**: >85% person detection accuracy (YOLOv11)
- **GPS Precision**: ±2.5m CEP GPS accuracy
- **Concurrent Streams**: Support for up to 10 simultaneous drone connections
- **Processing Speed**: 15-30 FPS object detection depending on model optimization

#### Model Optimization
- **FP32 Models**: High accuracy for cloud processing
- **INT8 Models**: Quantized models for edge computing on drones
- **Nano Models**: Ultra-lightweight models for resource-constrained devices
- **Dynamic Switching**: Automatic model selection based on hardware capabilities

#### Network Requirements
- **Bandwidth**: 2-5 Mbps per video stream (adaptive bitrate)
- **Latency**: <100ms network round-trip time for real-time operation
- **Reliability**: Automatic reconnection and stream recovery
- **Security**: WebRTC DTLS encryption for secure video transmission

#### Scalability Features
- **Horizontal Scaling**: Microservices can be independently scaled
- **Load Balancing**: Distributed processing across multiple analytics servers
- **Database Sharding**: GPS and detection data partitioned by mission/time
- **Caching Layer**: Redis-based caching for frequently accessed data

### Development Practices

#### Code Architecture
- **MVC Pattern**: Clear separation of concerns in web application
- **Service Layer**: Business logic abstracted into reusable services
- **Repository Pattern**: Data access layer for database operations
- **Event-Driven Design**: Asynchronous processing with Socket.IO events

#### Quality Assurance
- **Type Hints**: Python type annotations for better code maintainability
- **Error Handling**: Comprehensive exception handling with logging
- **Input Validation**: Request validation using Flask-WTF and custom validators
- **Testing Strategy**: Unit tests for core functions, integration tests for APIs

#### Performance Optimization
- **Async Processing**: Non-blocking I/O operations with asyncio
- **Connection Pooling**: Database connection reuse for efficiency
- **Memory Management**: Efficient model loading and GPU memory optimization
- **Caching Strategies**: Redis caching for frequently accessed data

#### Security Measures
- **Environment Variables**: Sensitive data stored in .env files
- **Input Sanitization**: XSS protection and SQL injection prevention
- **CORS Configuration**: Proper cross-origin resource sharing setup
- **API Authentication**: Token-based authentication for secure endpoints

#### Monitoring & Logging
- **Structured Logging**: JSON-formatted logs with correlation IDs
- **Performance Metrics**: Response time and throughput monitoring
- **Error Tracking**: Comprehensive error logging with stack traces
- **Health Checks**: Service health monitoring endpoints

### Future Roadmap

#### Planned Features
- **Thermal Imaging**: Integration with FLIR cameras for heat signature detection
- **3D Mapping**: LiDAR integration for terrain mapping and obstacle avoidance
- **Swarm Coordination**: Multi-drone autonomous coordination algorithms
- **Emergency Protocols**: Automated emergency response procedures
- **Offline Operation**: Local network operation without internet dependency

#### Technical Enhancements
- **Edge AI**: On-device model optimization for reduced latency
- **5G Integration**: High-bandwidth video streaming capabilities
- **Blockchain Logging**: Immutable mission logs for legal compliance
- **AR Overlays**: Augmented reality information overlay on video feeds
- **Predictive Analytics**: ML models for flood pattern prediction

#### Platform Extensions
- **Mobile App**: iOS/Android companion app for field operations
- **API Gateway**: Centralized API management and rate limiting
- **Multi-cloud**: Support for AWS, Azure, and GCP deployments
- **Container Orchestration**: Kubernetes deployment configurations
- **CI/CD Pipeline**: Automated testing and deployment workflows

#### Research Areas
- **Computer Vision**: Advanced object recognition and behavior analysis
- **Natural Language**: Multi-language voice command processing
- **IoT Integration**: Sensor network integration for environmental monitoring
- **Machine Learning**: Continuous model improvement with mission data
- **Human Factors**: UI/UX optimization for emergency response scenarios

### Team Structure & Roles

#### Core Development Team
- **Full-Stack Developer**: Flask backend, React frontend, database design
- **AI/ML Engineer**: Computer vision models, voice processing, model optimization
- **DevOps Engineer**: Infrastructure, deployment, monitoring, CI/CD pipelines
- **UI/UX Designer**: Interface design, user experience, responsive layouts
- **Embedded Systems Engineer**: Drone integration, hardware interfaces, optimization

#### Specialized Roles
- **Computer Vision Specialist**: YOLO model training, object detection algorithms
- **WebRTC Expert**: Real-time streaming, peer-to-peer communication protocols
- **GIS Specialist**: GPS systems, mapping integration, spatial data analysis
- **Security Engineer**: System security, data protection, compliance auditing
- **QA Engineer**: Test automation, performance testing, quality assurance

#### Domain Experts
- **Flood Rescue Specialist**: Emergency response procedures, rescue protocols
- **Drone Operations Expert**: UAV operations, flight planning, safety regulations
- **Data Analyst**: Mission data analysis, performance metrics, reporting
- **Technical Writer**: Documentation, user guides, API specifications

#### Project Management
- **Product Manager**: Feature prioritization, stakeholder management, roadmap planning
- **Scrum Master**: Agile process facilitation, team coordination, sprint planning
- **Technical Lead**: Architecture decisions, code reviews, technical mentoring
- **Quality Assurance Lead**: Testing strategy, quality standards, release management

## 🛠️ Technology Stack

### Backend
- **Python 3.8+**: Core programming language
- **Flask**: Web framework with MVC architecture
- **Flask-SocketIO**: Real-time bidirectional communication
- **aiortc**: WebRTC implementation for video streaming
- **OpenCV**: Computer vision and image processing
- **SQLite**: Lightweight database for data persistence

### AI/ML
- **YOLOv11**: Object detection model for person identification
- **Whisper**: Speech recognition for voice analysis
- **Phi-3**: Large language model for intent classification
- **Transformers**: Hugging Face library for model management

### Frontend
- **HTML5/CSS3**: Modern responsive design
- **JavaScript (ES6+)**: Client-side interactivity
- **Leaflet.js**: Interactive mapping library
- **Bootstrap**: UI component framework
- **Socket.IO Client**: Real-time communication

### Infrastructure
- **Docker**: Containerization support
- **Cloudinary**: Cloud storage for media files
- **WebRTC**: Peer-to-peer video communication
- **WebSocket**: Real-time data transmission

## 📋 Prerequisites

- Python 3.8 or higher
- Node.js 16+ (for development tools)
- Raspberry Pi or compatible hardware (for drone client)
- Webcam/camera device
- GPS module (optional, for location tracking)
- Internet connection for cloud services

## 🚀 Installation & Setup

### 1. Clone Repository
```bash
git clone https://github.com/HuyHoang04/sky-webapp.git
cd sky-webapp
```

### 2. Environment Configuration
Create `.env` files in each service directory by copying from the provided `.env.example` files:

#### Web Application (.env)
```bash
cd web-app
cp .env.example .env
# Edit .env with your actual values
```

#### Drone Application (.env)
```bash
cd ../drone-app
cp .env.example .env
# Edit .env with your actual values
```

#### Analytics Image Server (.env)
```bash
cd ../analytics-image-server
cp .env.example .env
# Edit .env with your actual values
```

#### Analytics Voice Server (.env)
```bash
cd ../analytics-voice-server
cp .env.example .env
# Edit .env with your actual values
```

#### Record System (.env)
```bash
cd ../record-system
cp .env.example .env
# Edit .env with your actual values
```

**Note**: Each service has a comprehensive `.env.example` file with all required environment variables documented. Replace placeholder values with your actual configuration before running the services.
```bash
# Web Application
cd web-app
pip install -r requirements.txt

# Drone Application
cd ../drone-app
pip install -r requirements.txt

# Analytics Image Server
cd ../analytics-image-server
pip install -r requirements.txt

# Analytics Voice Server
cd ../analytics-voice-server
pip install -r requirements.txt

# Record System
cd ../record-system
pip install -r requirements.txt
```

### 4. Database Initialization
```bash
cd web-app
python -c "from database import init_db; init_db()"
```

## 🎯 Usage

### Starting the System

1. **Web Application** (Terminal 1):
```bash
cd web-app
python app.py
```
Access dashboard at: http://localhost:5000

2. **Analytics Image Server** (Terminal 2):
```bash
cd analytics-image-server
python main.py
```
Runs on: http://localhost:8001

3. **Analytics Voice Server** (Terminal 3):
```bash
cd analytics-voice-server
python main.py
```
Runs on: http://localhost:8002

4. **Drone Client** (Terminal 4):
```bash
cd drone-app
python main.py --server-url http://localhost:5000 --device-id drone-camera
```

5. **Record System** (Optional, Terminal 5):
```bash
cd record-system
python main.py
```

### Web Dashboard Features

- **Video Grid**: Multi-camera view with layout switching
- **GPS Map**: Real-time drone location tracking
- **Detection Stats**: Live person counting (earth/sea)
- **Voice Commands**: Audio analysis and intent recognition
- **Mission Control**: Route planning and optimization

## 📡 API Documentation

### REST Endpoints

#### Video API
- `GET /api/video/streams` - List all video streams
- `GET /api/video/stream/{device_id}` - Get specific stream info
- `POST /api/video/start/{device_id}` - Start video stream
- `POST /api/video/stop/{device_id}` - Stop video stream

#### GPS API
- `GET /api/gps` - Get all GPS data
- `GET /api/gps/{device_id}` - Get device GPS data
- `POST /api/gps` - Submit GPS data

#### Detection API
- `GET /api/detection/stats` - Get detection statistics
- `POST /api/detection/analyze` - Analyze image for objects

#### Voice API
- `POST /api/voice/analyze` - Analyze audio for intent
- `GET /api/voice/results/{record_id}` - Get analysis results

### WebSocket Events

#### Video Events
- `webrtc_offer` - WebRTC connection offer
- `webrtc_answer` - WebRTC connection answer
- `webrtc_ice_candidate` - ICE candidate exchange
- `video_device_added` - New video device registration

#### GPS Events
- `gps_update` - GPS data update
- `gps_data` - Raw GPS data transmission

#### Detection Events
- `detection_update` - Object detection results
- `detection_result` - Detailed detection data

#### Voice Events
- `voice_analysis_complete` - Voice analysis finished
- `voice_transcription` - Audio transcription

## 🔧 Configuration

### Environment Variables
All sensitive configuration should be stored in `.env` files. Each service includes a comprehensive `.env.example` file with all required variables:

- `web-app/.env.example` - Flask application configuration
- `drone-app/.env.example` - Drone client configuration  
- `analytics-image-server/.env.example` - Image analytics service configuration
- `analytics-voice-server/.env.example` - Voice analytics service configuration
- `record-system/.env.example` - Audio recording system configuration

**Setup**: Copy `.env.example` to `.env` in each service directory and update with your actual values.

### Key Configuration Options

### Model Configuration
- YOLO models are stored in `drone-app/` directory
- Phi-3 model is loaded from Hugging Face
- Whisper model uses medium size for balance of speed/accuracy

## 🧪 Testing

### Unit Tests
```bash
cd web-app
python -m pytest tests/
```

### Integration Tests
```bash
# Test WebRTC connection
python test_webrtc.py

# Test GPS data flow
python test_gps.py

# Test detection pipeline
python test_detection.py
```

### Performance Testing
```bash
# Load testing with multiple drones
python load_test.py --drones 5 --duration 300
```
## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Guidelines
- Follow PEP 8 style guide
- Write comprehensive unit tests
- Update documentation for new features
- Ensure cross-platform compatibility

## 📝 License

This project is licensed under a Proprietary License - see the [LICENSE](LICENSE) file for details.

```
Copyright (c) 2025 HuyHoang04. All rights reserved.

This software and associated documentation files (the "Software") are proprietary
and confidential. Unauthorized copying, modification, distribution, or use of
this software is strictly prohibited.

Permission is granted solely to authorized users for personal or internal use
only, subject to the following conditions:

1. This software may not be copied, modified, or distributed without explicit
   written permission from the copyright holder.

2. This software may not be used for commercial purposes without a valid
   commercial license agreement.

3. Any use of this software must include proper attribution to the original
   author and copyright holder.

4. Reverse engineering, decompilation, or disassembly of this software is
   prohibited.

5. This software is provided "AS IS" without warranty of any kind, express or
   implied, including but not limited to the warranties of merchantability,
   fitness for a particular purpose, and noninfringement.

For licensing inquiries, please contact: [your-email@example.com]

THE SOFTWARE IS PROVIDED UNDER STRICT LICENSE TERMS. VIOLATION OF THESE TERMS
MAY RESULT IN LEGAL ACTION.
```

## 🙏 Acknowledgments

- YOLOv11 team for object detection models
- OpenAI for Whisper speech recognition
- Microsoft for Phi-3 language model
- aiortc community for WebRTC implementation
- Flask and Socket.IO communities

## 📞 Support

For support and questions:
- Create an issue on GitHub
- Contact: [lahuyhoang04@gmail.com]
- Documentation: [[link-to-docs](https://docs.google.com/document/d/126QZxoa8y4uUbx0oIrZQdPZO8DCSqkS_b8DdJgEEp-g/edit?usp=sharing)]

---

**Built with ❤️ for flood rescue operations**

**Copyright © 2025 HuyHoang04. All rights reserved.**

```
