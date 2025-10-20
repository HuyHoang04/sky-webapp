from flask import Flask
from socket_instance import socketio
from controller.main_controller import main_blueprint

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sky_webapp_secret_key'
socketio.init_app(app)

# Đăng ký main blueprint trước
app.register_blueprint(main_blueprint)

# Import các blueprint khác sau khi đã tạo app
from controller.video_controller import video_blueprint
from controller.gps_controller import gps_blueprint

# Đăng ký các blueprint còn lại
app.register_blueprint(video_blueprint)
app.register_blueprint(gps_blueprint)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)