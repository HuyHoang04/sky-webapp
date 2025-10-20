from flask import Blueprint, render_template

main_blueprint = Blueprint('main', __name__)

@main_blueprint.route('/')
def index():
    """
    Trang chủ của ứng dụng
    """
    return render_template('index.html')

@main_blueprint.route('/dashboard')
def dashboard():
    """
    Trang dashboard hiển thị video và dữ liệu GPS
    """
    return render_template('dashboard.html')