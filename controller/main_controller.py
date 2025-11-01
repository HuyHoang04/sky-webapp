from flask import Blueprint, render_template
import logging

logger = logging.getLogger(__name__)

main_blueprint = Blueprint('main', __name__)

@main_blueprint.route('/')
def index():
    return render_template('index.html')

@main_blueprint.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')