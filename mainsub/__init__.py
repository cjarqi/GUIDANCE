# GUIDANCE/mainsub/__init__.py

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_mail import Mail
import os
from datetime import datetime
from dotenv import load_dotenv

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

def create_app():
    load_dotenv()

    app = Flask(__name__, template_folder='templates', static_folder='static')

    # --- CONFIGURATION ---
    app.config['SECRET_KEY'] = 'your_very_secret_key_that_you_must_change_!"123$%^' 
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:cjarqi@localhost/guidance_db' 
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False
    upload_folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_folder_path, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder_path
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # --- MAIL CONFIGURATION ---
    app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = ('Guidance System', os.environ.get('MAIL_USERNAME'))
    
    # --- INITIALIZE EXTENSIONS ---
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db) 
    mail.init_app(app)

    # --- START: CORRECTED IMPORTS AND CONTEXT PROCESSOR ---
    # These must be inside create_app to avoid circular imports
    from .models import StaffUser, Notification, UserRole

    @login_manager.user_loader
    def load_user(user_id):
        return StaffUser.query.get(int(user_id))
        
    @app.context_processor
    def inject_global_variables():
        context = {
            'year': datetime.utcnow().year,
            'notifications': [],
            'unread_notification_count': 0,
            'UserRole': UserRole 
        }
        if current_user.is_authenticated:
            context['notifications'] = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).limit(10).all()
            context['unread_notification_count'] = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return context
    # --- END: CORRECTED IMPORTS AND CONTEXT PROCESSOR ---

    # --- LOGIN MANAGER CONFIGURATION ---
    login_manager.login_view = 'auth.login_page' 
    login_manager.login_message_category = 'info'

    # --- REGISTER BLUEPRINTS ---
    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .views import views_bp
    app.register_blueprint(views_bp, url_prefix='/')

    # --- DATABASE CREATION ---
    with app.app_context():
        db.create_all() 
        print("Database tables checked/created by db.create_all() (if not existing and not handled by migrations).")

    return app