from dotenv import load_dotenv
import logging
import os
import sys

# Load environment variables FIRST before any other imports
load_dotenv()

from flask import Flask
from socket_instance import socketio
from controller.main_controller import main_blueprint
from database import init_db, check_db_connection

# Configure logging with UTF-8 encoding for Windows compatibility
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('sky_webapp.log', encoding='utf-8')
    ]
)
# Set console encoding to UTF-8 for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'sky_webapp_secret_key')
app.config['DEBUG'] = os.getenv('FLASK_ENV', 'production') == 'development'

# Initialize SocketIO
socketio.init_app(app, cors_allowed_origins="*")

# Initialize database
logger.info("=" * 60)
logger.info("SkyAid Drone WebApp Starting...")
logger.info("=" * 60)

db_initialized = False
try:
    # Create database tables
    init_db()
    
    # Verify connection
    db_initialized = check_db_connection()
    
    if db_initialized:
        logger.info("✓ Database initialized successfully")
    else:
        logger.warning("⚠ Database connection could not be verified")
        logger.warning("  Application will run but database features may not work")
        logger.warning("  Please check your DATABASE_URL in .env file")
        
except Exception as e:
    # Only log error if database truly failed
    if not db_initialized:
        logger.error(f"✗ Database initialization failed: {e}")
        logger.warning("⚠ Application will start but database features will not work")

# Register blueprints
logger.info("Registering blueprints...")

# Register main blueprint first
app.register_blueprint(main_blueprint)

# Import and register other blueprints
from controller.video_controller import video_blueprint
from controller.gps_controller import gps_blueprint
from controller.mission_controller import mission_blueprint
from controller.detection_controller import detection_blueprint

app.register_blueprint(video_blueprint)
app.register_blueprint(gps_blueprint)
app.register_blueprint(mission_blueprint)
app.register_blueprint(detection_blueprint)

logger.info("✓ All blueprints registered")
logger.info("=" * 60)

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check endpoint for monitoring"""
    db_status = check_db_connection()
    return {
        'status': 'healthy' if db_status else 'degraded',
        'database': 'connected' if db_status else 'disconnected',
        'version': '1.0.0'
    }

if __name__ == '__main__':
    logger.info(f"Starting server on http://0.0.0.0:5000")
    logger.info(f"Debug mode: {app.config['DEBUG']}")
    logger.info("=" * 60)
    
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=5000, 
        debug=app.config['DEBUG'],
        allow_unsafe_werkzeug=True
    )