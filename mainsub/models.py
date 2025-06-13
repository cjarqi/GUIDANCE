from . import db
from flask import current_app
from flask_login import UserMixin
from itsdangerous import URLSafeTimedSerializer as Serializer
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import enum

class UserRole(enum.Enum):
    COUNSELOR = 'Guidance Counselor'
    DEAN = 'Dean'
    OSA_HEAD = 'Head of OSA'

class StaffUser(UserMixin, db.Model):
    __tablename__ = 'staff_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.COUNSELOR)
    is_active_staff = db.Column(db.Boolean, default=True, nullable=False) 
    
    reported_incidents = db.relationship('Incident', backref='reporter', lazy='dynamic', foreign_keys='Incident.reported_by_staff_id')
    assigned_incidents = db.relationship('Incident', backref='assignee', lazy='dynamic', foreign_keys='Incident.assigned_to_id')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    
    def get_reset_token(self):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except:
            return None
        return StaffUser.query.get(user_id)

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    
    @property
    def is_active(self): return self.is_active_staff

    def __repr__(self): 
        return f'<StaffUser {self.username} Role: {self.role.name}>'

class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    program_name = db.Column(db.String(150), unique=True, nullable=False)
    program_code = db.Column(db.String(20), unique=True, nullable=True)
    students = db.relationship('Student', backref='program', lazy='dynamic')
    def __repr__(self): return f'<Program {self.program_code} - {self.program_name}>'

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True) 
    student_number = db.Column(db.String(50), unique=True, nullable=False) 
    first_name = db.Column(db.String(100), nullable=False)
    # --- THIS IS THE NEW FIELD ---
    middle_name = db.Column(db.String(100), nullable=True) 
    # --- END OF NEW FIELD ---
    last_name = db.Column(db.String(100), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False)
    year_section = db.Column(db.String(10), nullable=False) 
    contact_info_email = db.Column(db.String(120), nullable=True)
    contact_info_phone = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Active') 
    incidents = db.relationship('Incident', backref='student', lazy='dynamic', cascade="all, delete-orphan", foreign_keys='Incident.student_id')
    
    @property
    def full_name(self):
        # --- THIS PROPERTY IS UPDATED ---
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"
        # --- END OF UPDATE ---
        
    def __repr__(self): return f'<Student {self.student_number}: {self.last_name}, {self.first_name} ({self.year_section})>'

class ViolationCatalog(db.Model):
    __tablename__ = 'violation_catalog'
    id = db.Column(db.Integer, primary_key=True)
    violation_code = db.Column(db.String(20), unique=True, nullable=False) 
    description = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False) 
    reference_page = db.Column(db.String(10), nullable=True) 
    is_inherently_major = db.Column(db.Boolean, default=False, nullable=False)
    def __repr__(self): return f'<Violation {self.violation_code} ({self.type}): {self.description[:30]}...>'

class Incident(db.Model):
    __tablename__ = 'incidents'
    id = db.Column(db.Integer, primary_key=True)
    date_committed = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    details = db.Column(db.Text, nullable=True)
    supporting_documents_path = db.Column(db.String(255), nullable=True) 
    status = db.Column(db.String(50), nullable=False, default='Pending Review') 
    is_escalated_to_major = db.Column(db.Boolean, default=False, nullable=False) 
    is_second_or_subsequent_major = db.Column(db.Boolean, default=False, nullable=False) 
    cheated_subject = db.Column(db.String(100), nullable=True) 
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    violation_id = db.Column(db.Integer, db.ForeignKey('violation_catalog.id'), nullable=False)
    reported_by_staff_id = db.Column(db.Integer, db.ForeignKey('staff_users.id'), nullable=True) 
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('staff_users.id'), nullable=True)
    violation = db.relationship('ViolationCatalog', backref=db.backref('incidents', lazy='dynamic'))
    sanction_applied = db.relationship('SanctionLog', backref='incident', uselist=False, lazy='joined', cascade="all, delete-orphan") 
    def __repr__(self): return f'<Incident {self.id} for Student {self.student_id} on {self.date_committed.strftime("%Y-%m-%d")}>'

class SanctionLog(db.Model):
    __tablename__ = 'sanctions_log'
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('incidents.id', ondelete='CASCADE'), unique=True, nullable=False) 
    sanction_type = db.Column(db.String(100), nullable=False) 
    sanction_details = db.Column(db.Text, nullable=True) 
    date_assigned = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=True)
    completion_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    def __repr__(self): return f'<SanctionLog {self.id} for Incident {self.incident_id} - Type: {self.sanction_type}>'

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('staff_users.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    def __repr__(self):
        return f'<AuditLog {self.id} by User {self.user_id}: {self.action}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('staff_users.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    link_url = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    def __repr__(self):
        return f'<Notification {self.id} for User {self.user_id}>'