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
    # Use environment variables for secret key and database URI for security and flexibility.
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-dev-that-is-still-secure')

    # Database configuration for production (e.g., Render) and local development
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("mysql://"):
        # The mysql-connector-python package requires 'mysql+mysqlconnector'
        # Render's DATABASE_URL provides 'mysql://', so we need to replace it.
        database_url = database_url.replace("mysql://", "mysql+mysqlconnector://", 1)

    # Use the environment variable if available, otherwise fall back to the local URI
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'mysql+mysqlconnector://root:cjarqi@localhost/guidance_db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False # Set to True for debugging SQL queries
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
            try:
                context['notifications'] = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).limit(10).all()
                context['unread_notification_count'] = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            except Exception:
                # This can fail during migrations or initial app startup before tables exist.
                # Fail gracefully to prevent the application from crashing.
                pass
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

    # --- DATABASE CREATION (COMMENTED OUT FOR PRODUCTION) ---
    # In a production environment with migrations, this should be disabled.
    # Database schema management should be handled by 'flask db upgrade' 
    # as part of the build/deploy process, not by db.create_all().
    #
    # with app.app_context():
    #     db.create_all() 
    #     print("!!! WARNING: db.create_all() was called. This is not recommended for production with migrations.")

    return app