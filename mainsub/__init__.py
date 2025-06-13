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
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secure-default-secret-key-for-development')

    # --- DATABASE CONFIGURATION (Production and Local) ---
    
    # Check for a single DATABASE_URL environment variable (standard for production)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # If we're in production (DATABASE_URL is set), use it.
        # Render provides a 'mysql://' URL, but mysql-connector-python requires 'mysql+mysqlconnector://'
        if database_url.startswith("mysql://"):
            database_url = database_url.replace("mysql://", "mysql+mysqlconnector://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # If we're local (DATABASE_URL is not set), build the URI from your local defaults.
        # This part will now ONLY run on your local machine.
        DEFAULT_DB_HOST = 'localhost'
        DEFAULT_DB_USER = 'root'
        DEFAULT_DB_PASSWORD = "cjarqi"
        DEFAULT_DB_NAME = "guidance_db"
        DEFAULT_DB_PORT = '3306'
        
        local_sqlalchemy_uri = (
            f"mysql+mysqlconnector://{DEFAULT_DB_USER}:{DEFAULT_DB_PASSWORD}@"
            f"{DEFAULT_DB_HOST}:{DEFAULT_DB_PORT}/{DEFAULT_DB_NAME}"
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = local_sqlalchemy_uri

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False # Set to True for debugging SQL queries

    # --- End of new database configuration ---

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

    # --- START: IMPORTS AND CONTEXT PROCESSOR ---
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
            try:
                context['notifications'] = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).limit(10).all()
                context['unread_notification_count'] = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            except Exception:
                pass
        return context
    # --- END: IMPORTS AND CONTEXT PROCESSOR ---

    # --- LOGIN MANAGER CONFIGURATION ---
    login_manager.login_view = 'auth.login_page' 
    login_manager.login_message_category = 'info'

    # --- REGISTER BLUEPRINTS ---
    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .views import views_bp
    app.register_blueprint(views_bp, url_prefix='/')

    return app