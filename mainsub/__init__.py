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

    # --- DATABASE CONFIGURATION (For Aiven or other external DBs) ---

    # 1. Define the default parameters for LOCAL development ONLY
    LOCAL_DB_HOST = 'localhost'
    LOCAL_DB_USER = 'root'
    LOCAL_DB_PASSWORD = "cjarqi"
    LOCAL_DB_NAME = "guidance_db"
    LOCAL_DB_PORT = '3306'

    # 2. Get connection parameters from environment variables.
    #    On Render, these MUST be set with your Aiven credentials.
    #    If not found, it falls back to your local settings (which fails on Render).
    db_host = os.environ.get('DB_HOST', LOCAL_DB_HOST)
    db_user = os.environ.get('DB_USER', LOCAL_DB_USER)
    db_password = os.environ.get('DB_PASSWORD', LOCAL_DB_PASSWORD)
    db_name = os.environ.get('DB_NAME', LOCAL_DB_NAME)
    db_port = os.environ.get('DB_PORT', LOCAL_DB_PORT)
    
    # Add a print statement for debugging in the Render logs
    print(f"--- DATABASE CONNECTION ATTEMPT ---")
    print(f"Connecting to Host: {db_host}")
    print(f"Connecting on Port: {db_port}")
    print(f"Connecting as User: {db_user}")
    print(f"Connecting to DB:   {db_name}")
    print(f"---------------------------------")


    # 3. Construct the final SQLAlchemy Database URI string
    sqlalchemy_uri = (
        f"mysql+mysqlconnector://{db_user}:{db_password}@"
        f"{db_host}:{db_port}/{db_name}"
    )
    
    app.config['SQLALCHEMY_DATABASE_URI'] = sqlalchemy_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = False

    # --- End of database configuration ---

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