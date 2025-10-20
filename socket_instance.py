from flask_socketio import SocketIO

# Tạo instance SocketIO để sử dụng trong toàn bộ ứng dụng
socketio = SocketIO(cors_allowed_origins="*")

def get_socketio():
    return socketio