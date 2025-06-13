#views.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app, send_from_directory
from flask_login import login_required, current_user
from .models import db, Incident, Student, ViolationCatalog, StaffUser, Program, SanctionLog, AuditLog, Notification, UserRole
from sqlalchemy import func, distinct, or_, and_, cast, Date
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta, date
import re
import os
import uuid
from werkzeug.utils import secure_filename
import pandas as pd

views_bp = Blueprint('views', __name__)

def log_audit(action, target_type=None, target_id=None, details=None):
    try:
        log_entry = AuditLog(user_id=current_user.id, action=action, target_type=target_type, target_id=target_id, details=details)
        db.session.add(log_entry)
    except Exception as e:
        print(f"!!! CRITICAL: Failed to create audit log: {e}")

def create_notification(user, message, link_url):
    try:
        notification = Notification(user_id=user.id, message=message, link_url=link_url)
        db.session.add(notification)
    except Exception as e:
        print(f"!!! CRITICAL: Failed to create notification: {e}")

@views_bp.route('/')
@views_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        active_incidents_count = Incident.query.filter(~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])).count()
        pending_major_sanctions_count = Incident.query.join(Incident.violation).filter(
            (ViolationCatalog.type == 'Major') | (Incident.is_escalated_to_major == True),
            Incident.status.in_(['Pending Major Sanction Review', 'Pending Review', 'Escalated'])
        ).count()
        active_minor_offenses_subquery = db.session.query(Incident.student_id, func.count(Incident.id).label('active_minor_count')).join(Incident.violation).filter(ViolationCatalog.type == 'Minor', Incident.is_escalated_to_major == False, ~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])).group_by(Incident.student_id).subquery()
        students_at_risk_count = db.session.query(func.count(active_minor_offenses_subquery.c.student_id)).filter(active_minor_offenses_subquery.c.active_minor_count == 2).scalar() or 0
        recent_incidents_list = Incident.query.options(joinedload(Incident.student).joinedload(Student.program), joinedload(Incident.violation)).order_by(Incident.date_committed.desc()).limit(5).all()
        available_students = Student.query.order_by(Student.last_name, Student.first_name).all()
        minor_violations = ViolationCatalog.query.filter_by(type='Minor').order_by(ViolationCatalog.description).all()
        major_violations = ViolationCatalog.query.filter_by(type='Major').order_by(ViolationCatalog.description).all()
        now_iso_for_input = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
        return render_template('dashboard.html', 
                               current_user=current_user, 
                               active_incidents_count=active_incidents_count, 
                               pending_major_sanctions_count=pending_major_sanctions_count, 
                               students_at_risk_count=students_at_risk_count, 
                               recent_incidents=recent_incidents_list, 
                               available_students=available_students, 
                               minor_violations=minor_violations, 
                               major_violations=major_violations, 
                               now_iso=now_iso_for_input)
    except Exception as e:
        print(f"!!! Critical Error in dashboard route: {e} !!!"); import traceback; print(traceback.format_exc()) 
        flash("A critical error occurred while loading the dashboard. Administrators have been notified.", "error"); abort(500)

@views_bp.route('/log_incident', methods=['POST'])
@login_required
def log_incident():
    if request.method == 'POST':
        student_id_str = request.form.get('student_id'); violation_id_str = request.form.get('violation_id'); date_committed_str = request.form.get('date_committed'); details = request.form.get('details'); cheated_subject = request.form.get('cheated_subject', None); file = request.files.get('supporting_document'); saved_filename = None
        if file and file.filename != '':
            if not allowed_file(file.filename): flash('Invalid file type. Allowed types are: png, jpg, jpeg, gif, pdf, doc, docx, txt.', 'error'); return redirect(request.referrer)
            filename = secure_filename(file.filename); unique_prefix = uuid.uuid4().hex[:8]; saved_filename = f"{unique_prefix}_{filename}"
            try: file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], saved_filename))
            except Exception as e: flash(f'Error saving file: {str(e)}', 'error'); return redirect(request.referrer)
        if not all([student_id_str, violation_id_str, date_committed_str, details]): flash('Missing required fields.', 'error'); return redirect(request.referrer)
        try: student_id = int(student_id_str); violation_id = int(violation_id_str); date_committed = datetime.fromisoformat(date_committed_str)
        except ValueError: flash('Invalid data format.', 'error'); return redirect(request.referrer)
        student = Student.query.get(student_id); violation = ViolationCatalog.query.get(violation_id)
        if not student or not violation: flash('Invalid student or violation.', 'error'); return redirect(request.referrer)
        is_currently_major_offense = False; is_escalated_to_major_for_this_incident = False 
        if violation.type == 'Minor':
            previous_minor_offenses_count = Incident.query.join(Incident.violation).filter(Incident.student_id == student_id, ViolationCatalog.type == 'Minor', Incident.is_escalated_to_major == False, ~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])).count()
            if previous_minor_offenses_count >= 2: is_escalated_to_major_for_this_incident = True; is_currently_major_offense = True 
        elif violation.type == 'Major': is_currently_major_offense = True
        incident_status = "Pending Review"; is_second_or_subsequent_major_flag = False
        if is_currently_major_offense:
            incident_status = "Pending Major Sanction Review"
            prior_major_incidents_count = Incident.query.join(Incident.violation).filter(Incident.student_id == student_id, Incident.date_committed < date_committed, or_(ViolationCatalog.type == 'Major', Incident.is_escalated_to_major == True)).count()
            if prior_major_incidents_count >= 1: is_second_or_subsequent_major_flag = True
        new_incident = Incident(student_id=student_id, violation_id=violation_id, date_committed=date_committed, details=details, reported_by_staff_id=current_user.id, status=incident_status, is_escalated_to_major=is_escalated_to_major_for_this_incident, is_second_or_subsequent_major=is_second_or_subsequent_major_flag, cheated_subject=cheated_subject if (violation.description.lower().find('cheating') != -1 or violation.description.lower().find('academic dishonesty') != -1) and cheated_subject else None, supporting_documents_path=saved_filename)
        db.session.add(new_incident)
        try:
            db.session.flush()
            log_audit("Created Incident", "Incident", new_incident.id, f"For student {student.first_name} {student.last_name}")
            if is_currently_major_offense:
                all_staff_to_notify = StaffUser.query.filter_by(is_active_staff=True).all()
                for staff in all_staff_to_notify:
                    if staff.id != current_user.id:
                        create_notification(user=staff, message=f"New major offense logged for {student.first_name} {student.last_name}.", link_url=url_for('views.incident_details', incident_id=new_incident.id))
            db.session.commit(); flash(f'Incident logged for {student.first_name} {student.last_name}.', 'success')
            if is_second_or_subsequent_major_flag: flash('ALERT: This is a second or subsequent major offense for this student!', 'warning')
            if violation.type == 'Minor' and not is_escalated_to_major_for_this_incident:
                current_minor_offenses_count = Incident.query.join(Incident.violation).filter(Incident.student_id == student_id, ViolationCatalog.type == 'Minor', Incident.is_escalated_to_major == False, ~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])).count()
                sanction_detail_text = ""
                if current_minor_offenses_count == 1: sanction_detail_text = "10 hours Community Extension"
                elif current_minor_offenses_count == 2: sanction_detail_text = "24 hours Community Service"
                if sanction_detail_text:
                    new_sanction = SanctionLog(incident_id=new_incident.id, sanction_type="Minor Offense Sanction", sanction_details=sanction_detail_text, date_assigned=datetime.utcnow())
                    db.session.add(new_sanction); new_incident.status = "Sanction Assigned"; db.session.flush()
                    log_audit("Auto-Assigned Minor Sanction", "SanctionLog", new_sanction.id, f"For Incident #{new_incident.id}")
                    db.session.commit(); flash(f"Automatic Sanction Applied: {sanction_detail_text}", "info")
        except Exception as e: db.session.rollback(); flash(f'Error logging incident: {str(e)}', 'error')
        return redirect(request.referrer or url_for('views.dashboard'))
    return redirect(url_for('views.dashboard'))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@views_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    try:
        return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=False)
    except FileNotFoundError:
        abort(404)

@views_bp.route('/notification/<int:notification_id>/mark-as-read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@views_bp.route('/notifications/mark-all-as-read', methods=['POST'])
@login_required
def mark_all_notifications_as_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return redirect(request.referrer or url_for('views.dashboard'))

@views_bp.route('/get_student_offense_info/<int:student_id>')
@login_required
def get_student_offense_info(student_id):
    student = Student.query.get_or_404(student_id)
    minor_offenses_count = Incident.query.join(Incident.violation).filter(Incident.student_id == student_id, ViolationCatalog.type == 'Minor', Incident.is_escalated_to_major == False, ~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])).count()
    return jsonify({'student_name': f"{student.first_name} {student.last_name}", 'minor_offense_count': minor_offenses_count})

@views_bp.route('/students', methods=['GET'])
@login_required
def student_list():
    selected_program_id = request.args.get('program', default=None, type=int)
    search_year_section = request.args.get('year_section_query', type=str, default="").strip()
    search_query = request.args.get('q', type=str, default="").strip()
    
    query = Student.query.options(db.joinedload(Student.program))
    if selected_program_id: query = query.filter(Student.program_id == selected_program_id)
    if search_year_section: query = query.filter(Student.year_section.ilike(f"%{search_year_section}%"))
    if search_query: search_term = f"%{search_query}%"; query = query.filter(db.or_(Student.first_name.ilike(search_term), Student.last_name.ilike(search_term), (Student.first_name + " " + Student.last_name).ilike(search_term), Student.student_number.ilike(search_term)))
    filtered_students = query.order_by(Student.last_name, Student.first_name).all() 
    
    programs_for_filter = Program.query.order_by(Program.program_name).all()
    available_students_for_modal = Student.query.order_by(Student.last_name, Student.first_name).all()
    minor_violations_for_modal = ViolationCatalog.query.filter_by(type='Minor').order_by(ViolationCatalog.description).all()
    major_violations_for_modal = ViolationCatalog.query.filter_by(type='Major').order_by(ViolationCatalog.description).all()
    now_iso_for_modal = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
    
    return render_template('students/list.html', 
                           current_user=current_user, 
                           students=filtered_students, 
                           programs_for_filter=programs_for_filter, 
                           page_title="Student Records", 
                           available_students=available_students_for_modal, 
                           minor_violations=minor_violations_for_modal, 
                           major_violations=major_violations_for_modal, 
                           now_iso=now_iso_for_modal,
                           selected_program_id=selected_program_id)

@views_bp.route('/students/add', methods=['GET', 'POST'])
@login_required
def add_student():
    programs_for_filter = Program.query.order_by(Program.program_name).all()
    if request.method == 'POST':
        student_number = request.form.get('student_number','').strip()
        first_name = request.form.get('first_name','').strip()
        middle_name = request.form.get('middle_name', '').strip()
        last_name = request.form.get('last_name','').strip()
        program_id_str = request.form.get('program_id')
        year_section = request.form.get('year_section', '').strip().upper()
        contact_email = request.form.get('contact_email', '').strip()
        contact_phone = request.form.get('contact_phone', '').strip()
        status = 'Active'
        
        errors = []
        if not student_number: errors.append("Student ID Number is required.")
        elif Student.query.filter_by(student_number=student_number).first(): errors.append(f"Student ID Number '{student_number}' already exists.")
        if not first_name: errors.append("First name is required.")
        if not last_name: errors.append("Last name is required.")
        
        program_id = None
        if program_id_str and program_id_str.isdigit():
            program_id = int(program_id_str)
            if not Program.query.get(program_id):
                errors.append("Invalid program selected.")
                program_id = None
        elif not program_id_str: errors.append("Program selection is required.")
        else: errors.append("Invalid program ID format.")

        if not year_section: errors.append("Year & Section is required.")
        elif not re.match(r"^[1-5][A-Za-z0-9]+$", year_section): errors.append("Year & Section format invalid (e.g., 1A, 2B1).")
        
        if errors:
            for error in errors: flash(error, 'error')
            return render_template('students/add_student.html', programs_for_filter=programs_for_filter, page_title="Add New Student")
        
        try:
            new_student = Student(
                student_number=student_number, 
                first_name=first_name, 
                middle_name=middle_name if middle_name else None,
                last_name=last_name, 
                program_id=program_id, 
                year_section=year_section, 
                contact_info_email=contact_email or None, 
                contact_info_phone=contact_phone or None, 
                status=status
            )
            db.session.add(new_student)
            db.session.flush()
            log_audit("Created Student", "Student", new_student.id, f"Created student {new_student.full_name} ({new_student.student_number})")
            db.session.commit()
            flash(f'Student {new_student.full_name} (ID: {student_number}) added successfully!', 'success')
            return redirect(url_for('views.student_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding student: {str(e)}', 'error')
            return render_template('students/add_student.html', programs_for_filter=programs_for_filter, page_title="Add New Student")

    return render_template('students/add_student.html', programs_for_filter=programs_for_filter, page_title="Add New Student")

@views_bp.route('/student/<int:student_id>/data', methods=['GET'])
@login_required
def get_student_data(student_id):
    student = Student.query.get_or_404(student_id)
    return jsonify({"id": student.id, "student_number": student.student_number, "first_name": student.first_name, "last_name": student.last_name, "program_id": student.program_id, "year_section": student.year_section, "contact_email": student.contact_info_email or "", "contact_phone": student.contact_info_phone or "", "status": student.status})

@views_bp.route('/student/<int:student_id>/edit', methods=['POST'])
@login_required
def edit_student(student_id):
    student_to_edit = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        first_name = request.form.get('first_name','').strip(); last_name = request.form.get('last_name','').strip(); program_id_str = request.form.get('program_id'); year_section = request.form.get('year_section', '').strip().upper(); contact_email = request.form.get('contact_email', '').strip(); contact_phone = request.form.get('contact_phone', '').strip(); status = request.form.get('status', 'Active')
        errors = []
        if not first_name: errors.append("First name is required.")
        if not last_name: errors.append("Last name is required.")
        program_id = None
        if program_id_str and program_id_str.isdigit():
            program_id = int(program_id_str)
            if not Program.query.get(program_id): errors.append("Invalid program selected."); program_id = None
        elif not program_id_str: errors.append("Program selection is required.")
        else: errors.append("Invalid program ID format.")
        if not year_section: errors.append("Year & Section is required.")
        elif not re.match(r"^[1-5][A-Za-z0-9]+$", year_section): errors.append("Year & Section format invalid (e.g., 1A, 2B1).")
        if errors:
            for error in errors: flash(error, 'error')
        else:
            try:
                student_to_edit.first_name = first_name; student_to_edit.last_name = last_name; student_to_edit.program_id = program_id; student_to_edit.year_section = year_section; student_to_edit.contact_info_email = contact_email if contact_email else None; student_to_edit.contact_info_phone = contact_phone if contact_phone else None; student_to_edit.status = status
                log_audit("Edited Student", "Student", student_to_edit.id, f"Edited student {student_to_edit.first_name} {student_to_edit.last_name}")
                db.session.commit(); flash(f'Student {student_to_edit.first_name} {student_to_edit.last_name} updated successfully!', 'success')
            except Exception as e: db.session.rollback(); flash(f'Error updating student: {str(e)}', 'error')
        return redirect(url_for('views.student_profile', student_id=student_to_edit.id)) 
    return redirect(url_for('views.student_profile', student_id=student_id))

@views_bp.route('/student/<int:student_id>')
@login_required
def student_profile(student_id):
    student = Student.query.options(joinedload(Student.program)).get_or_404(student_id)
    active_minor_offense_count = Incident.query.join(ViolationCatalog).filter(
        Incident.student_id == student_id,
        ViolationCatalog.type == 'Minor',
        Incident.is_escalated_to_major == False,
        ~Incident.status.in_(['Resolved', 'Sanction Completed', 'Closed'])
    ).count()
    major_offense_count = Incident.query.join(ViolationCatalog).filter(
        Incident.student_id == student_id,
        or_(
            ViolationCatalog.type == 'Major',
            Incident.is_escalated_to_major == True
        )
    ).count()
    incidents_with_sanctions_query = db.session.query(Incident, SanctionLog).select_from(Incident).outerjoin(SanctionLog, Incident.id == SanctionLog.incident_id).filter(Incident.student_id == student_id).options(joinedload(Incident.violation)).order_by(Incident.date_committed.desc()).all()
    programs_for_filter = Program.query.order_by(Program.program_name).all() 
    available_students = Student.query.order_by(Student.last_name, Student.first_name).all()
    minor_violations = ViolationCatalog.query.filter_by(type='Minor').order_by(ViolationCatalog.description).all()
    major_violations = ViolationCatalog.query.filter_by(type='Major').order_by(ViolationCatalog.description).all()
    now_iso_for_input = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
    return render_template('students/profile.html', 
                           student=student, 
                           incidents_with_sanctions=incidents_with_sanctions_query, 
                           programs_for_filter=programs_for_filter, 
                           current_user=current_user, 
                           available_students=available_students, 
                           minor_violations=minor_violations, 
                           major_violations=major_violations, 
                           now_iso=now_iso_for_input,
                           active_minor_offense_count=active_minor_offense_count,
                           major_offense_count=major_offense_count)

@views_bp.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student_to_delete = Student.query.get_or_404(student_id)
    if student_to_delete.incidents.count() > 0:
        flash(f'Cannot delete student "{student_to_delete.first_name} {student_to_delete.last_name}" because they have incident records. Please change their status to Inactive or Transferred Out instead.', 'error')
        return redirect(url_for('views.student_profile', student_id=student_id))
    try:
        student_name = f"{student_to_delete.first_name} {student_to_delete.last_name}"
        log_audit("Deleted Student", "Student", student_to_delete.id, f"Deleted student {student_name} ({student_to_delete.student_number})")
        db.session.delete(student_to_delete)
        db.session.commit()
        flash(f'Student "{student_name}" has been permanently deleted.', 'success')
        return redirect(url_for('views.student_list'))
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while trying to delete the student: {str(e)}', 'error')
        return redirect(url_for('views.student_profile', student_id=student_id))

@views_bp.route('/incidents')
@login_required
def incident_records_list():
    page = request.args.get('page', 1, type=int); per_page = 15; student_query_str = request.args.get('student_query', '').strip(); violation_type_filter = request.args.get('violation_type', '').strip(); status_filter = request.args.get('status', '').strip(); date_from_str = request.args.get('date_from', '').strip(); date_to_str = request.args.get('date_to', '').strip(); alert_trigger = request.args.get('alert_trigger', '').strip()
    page_title = "Incident Records"
    query = Incident.query.join(Student, Incident.student_id == Student.id).join(ViolationCatalog, Incident.violation_id == ViolationCatalog.id).outerjoin(StaffUser, Incident.reported_by_staff_id == StaffUser.id).options(joinedload(Incident.student).joinedload(Student.program), joinedload(Incident.violation), joinedload(Incident.reporter))
    if alert_trigger == 'urgent_major_review': query = query.filter(Incident.status.in_(['Pending Major Sanction Review', 'Escalated'])); page_title = "Urgent: Incidents Awaiting Major Sanction Review"
    if student_query_str: search_term = f"%{student_query_str}%"; query = query.filter(or_(Student.first_name.ilike(search_term), Student.last_name.ilike(search_term), (Student.first_name + " " + Student.last_name).ilike(search_term), Student.student_number.ilike(search_term)))
    if violation_type_filter: query = query.filter(ViolationCatalog.type == violation_type_filter)
    if status_filter and not alert_trigger == 'urgent_major_review': query = query.filter(Incident.status == status_filter)
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            query = query.filter(cast(Incident.date_committed, Date) >= date_from)
        except ValueError: flash('Invalid "Date From" format. Please use YYYY-MM-DD.', 'error')
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            query = query.filter(cast(Incident.date_committed, Date) <= date_to)
        except ValueError: flash('Invalid "Date To" format. Please use YYYY-MM-DD.', 'error')
    query = query.order_by(Incident.date_committed.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    distinct_statuses_query = db.session.query(Incident.status).distinct().order_by(Incident.status).all()
    distinct_statuses = [status[0] for status in distinct_statuses_query]
    available_students_for_modal = Student.query.order_by(Student.last_name, Student.first_name).all()
    minor_violations_for_modal = ViolationCatalog.query.filter_by(type='Minor').order_by(ViolationCatalog.description).all()
    major_violations_for_modal = ViolationCatalog.query.filter_by(type='Major').order_by(ViolationCatalog.description).all()
    now_iso_for_modal = datetime.utcnow().strftime('%Y-%m-%dT%H:%M');
    return render_template('incidents/list.html', current_user=current_user, pagination=pagination, distinct_statuses=distinct_statuses, available_students=available_students_for_modal, minor_violations=minor_violations_for_modal, major_violations=major_violations_for_modal, now_iso=now_iso_for_modal, page_title=page_title)

@views_bp.route('/incident/<int:incident_id>/details')
@login_required
def incident_details(incident_id):
    incident = Incident.query.options(joinedload(Incident.student).joinedload(Student.program), joinedload(Incident.violation), joinedload(Incident.reporter), joinedload(Incident.assignee)).get_or_404(incident_id)
    potential_assignees = StaffUser.query.filter(StaffUser.role.in_([UserRole.DEAN, UserRole.OSA_HEAD])).all()
    available_students_for_modal = Student.query.order_by(Student.last_name, Student.first_name).all() 
    minor_violations_for_modal = ViolationCatalog.query.filter_by(type='Minor').order_by(ViolationCatalog.description).all()
    major_violations_for_modal = ViolationCatalog.query.filter_by(type='Major').order_by(ViolationCatalog.description).all()
    return render_template('incidents/details.html',
                           incident=incident,
                           potential_assignees=potential_assignees,
                           current_user=current_user,
                           page_title=f"Incident #{incident.id}", 
                           available_students=available_students_for_modal, 
                           minor_violations=minor_violations_for_modal, 
                           major_violations=major_violations_for_modal, 
                           now_iso=datetime.utcnow().strftime('%Y-%m-%dT%H:%M'))

@views_bp.route('/incident/<int:incident_id>/delete', methods=['POST'])
@login_required
def delete_incident(incident_id):
    incident_to_delete = Incident.query.get_or_404(incident_id)
    if incident_to_delete.supporting_documents_path:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], incident_to_delete.supporting_documents_path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
                flash(f'Could not delete the associated file, but the incident record will still be removed. Please check the uploads folder.', 'warning')
    try:
        student_id_for_redirect = incident_to_delete.student_id
        student_name = f"{incident_to_delete.student.first_name} {incident_to_delete.student.last_name}"
        log_audit("Deleted Incident", "Incident", incident_id, f"Deleted Incident for student {student_name}")
        db.session.delete(incident_to_delete)
        db.session.commit()
        flash(f'Incident #{incident_id} has been permanently deleted.', 'success')
        return redirect(url_for('views.student_profile', student_id=student_id_for_redirect))
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while trying to delete the incident: {str(e)}', 'error')
        return redirect(url_for('views.incident_details', incident_id=incident_id))

@views_bp.route('/incident/<int:incident_id>/assign_sanction', methods=['POST'])
@login_required
def assign_major_sanction(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    if not (incident.status == 'Pending Major Sanction Review' or (incident.violation and incident.violation.type == 'Major' and incident.status == 'Pending Review') or (incident.is_escalated_to_major and incident.status == 'Pending Review')):
        flash('This incident is not currently awaiting a major sanction assignment.', 'warning'); return redirect(request.referrer or url_for('views.incident_records_list'))
    sanction_type = request.form.get('sanction_type'); sanction_details = request.form.get('sanction_details'); due_date_str = request.form.get('due_date'); notes = request.form.get('notes')
    if not sanction_type or not sanction_details: flash('Sanction Type and Details are required.', 'error'); return redirect(request.referrer or url_for('views.incident_details', incident_id=incident_id))
    due_date_to_save = None
    if due_date_str:
        try: due_date_to_save = datetime.strptime(due_date_str, '%Y-%m-%d')
        except ValueError: flash('Invalid Due Date format. Please use YYYY-MM-DD.', 'error'); return redirect(request.referrer or url_for('views.incident_details', incident_id=incident_id))
    existing_sanction = SanctionLog.query.filter_by(incident_id=incident.id).first()
    if existing_sanction:
        existing_sanction.sanction_type = sanction_type; existing_sanction.sanction_details = sanction_details; existing_sanction.date_assigned = datetime.utcnow() ; existing_sanction.due_date = due_date_to_save; existing_sanction.notes = notes; existing_sanction.completion_date = None 
        flash_message = 'Sanction updated successfully.'
        log_audit("Updated Sanction", "SanctionLog", existing_sanction.id, f"Updated sanction for Incident #{incident.id}")
    else:
        new_sanction = SanctionLog(incident_id=incident.id, sanction_type=sanction_type, sanction_details=sanction_details, date_assigned=datetime.utcnow(), due_date=due_date_to_save, notes=notes)
        db.session.add(new_sanction)
        db.session.flush()
        log_audit("Assigned Sanction", "SanctionLog", new_sanction.id, f"Assigned sanction '{sanction_type}' for Incident #{incident.id}")
        flash_message = 'Major sanction assigned successfully.'
    incident.status = "Sanction Assigned"
    if incident.reporter and incident.reporter.id != current_user.id:
        create_notification(user=incident.reporter, message=f"A sanction has been assigned for your reported incident #{incident.id}.", link_url=url_for('views.incident_details', incident_id=incident.id))
    try: db.session.commit(); flash(flash_message, 'success')
    except Exception as e: db.session.rollback(); flash(f'Error assigning sanction: {str(e)}', 'error')
    return redirect(url_for('views.incident_details', incident_id=incident.id))

@views_bp.route('/incident/<int:incident_id>/escalate', methods=['POST'])
@login_required
def escalate_incident(incident_id):
    incident = Incident.query.get_or_404(incident_id)
    assignee_id = request.form.get('assignee_id')
    if not assignee_id:
        flash('You must select a person to escalate the case to.', 'error')
        return redirect(url_for('views.incident_details', incident_id=incident_id))
    assignee = StaffUser.query.get(assignee_id)
    if not assignee or assignee.role not in [UserRole.DEAN, UserRole.OSA_HEAD]:
        flash('Invalid assignee selected.', 'error')
        return redirect(url_for('views.incident_details', incident_id=incident_id))
    incident.status = "Escalated"
    incident.assigned_to_id = assignee.id
    log_audit(action="Escalated Incident", target_type="Incident", target_id=incident.id, details=f"Case escalated to {assignee.role.value} {assignee.full_name}.")
    create_notification(user=assignee, message=f"Incident #{incident.id} for {incident.student.full_name} has been escalated to you for review.", link_url=url_for('views.incident_details', incident_id=incident.id))
    db.session.commit()
    flash(f'Incident #{incident.id} has been escalated to {assignee.full_name}.', 'success')
    return redirect(url_for('views.incident_details', incident_id=incident.id))

@views_bp.route('/my-cases')
@login_required
def my_cases():
    if current_user.role not in [UserRole.DEAN, UserRole.OSA_HEAD]:
        flash('You do not have permission to view this page.', 'error')
        return redirect(url_for('views.dashboard'))
    cases = Incident.query.filter_by(assigned_to_id=current_user.id).options(
        joinedload(Incident.student),
        joinedload(Incident.violation)
    ).order_by(Incident.date_committed.desc()).all()
    return render_template('my_cases.html', cases=cases, page_title="My Assigned Cases")

@views_bp.route('/sanction/<int:sanction_log_id>/complete', methods=['POST'])
@login_required
def complete_sanction(sanction_log_id):
    sanction = SanctionLog.query.get_or_404(sanction_log_id); incident = Incident.query.get(sanction.incident_id) 
    if not incident: flash('Associated incident not found for this sanction.', 'error'); return redirect(url_for('views.incident_records_list'))
    if sanction.completion_date: flash('This sanction has already been marked as completed.', 'info'); return redirect(url_for('views.incident_details', incident_id=incident.id))
    sanction.completion_date = datetime.utcnow(); incident.status = "Sanction Completed" 
    try: 
        log_audit("Completed Sanction", "SanctionLog", sanction.id, f"Marked sanction for Incident #{incident.id} as completed.")
        db.session.commit(); flash(f'Sanction for Incident #{incident.id} marked as completed.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Error marking sanction as completed: {str(e)}', 'error')
    return redirect(url_for('views.incident_details', incident_id=incident.id))

# === VIOLATION CATALOG MANAGEMENT ROUTES ===
@views_bp.route('/settings/violations')
@login_required
def violation_catalog_list():
    violations = ViolationCatalog.query.order_by(ViolationCatalog.type.desc(), ViolationCatalog.violation_code).all()
    return render_template('settings/violations/list.html', violations=violations, current_user=current_user, page_title="Violation Catalog Management")

@views_bp.route('/settings/violations/add', methods=['GET', 'POST'])
@login_required
def add_violation():
    if request.method == 'POST':
        code = request.form.get('violation_code', '').strip().upper(); description = request.form.get('description', '').strip(); type_ = request.form.get('type'); ref_page = request.form.get('reference_page', '').strip(); is_inherently_major = 'is_inherently_major' in request.form 
        errors = []
        if not code: errors.append("Violation Code is required.")
        elif len(code) > 20: errors.append("Violation Code cannot exceed 20 characters.")
        elif ViolationCatalog.query.filter_by(violation_code=code).first(): errors.append(f"Violation Code '{code}' already exists.")
        if not description: errors.append("Description is required.")
        if type_ not in ['Minor', 'Major']: errors.append("Invalid Violation Type selected.")
        if ref_page and len(ref_page) > 10: errors.append("Reference Page cannot exceed 10 characters.")
        if errors:
            for error in errors: flash(error, 'error')
            form_data_for_template = {'violation_code': code, 'description': description, 'type': type_, 'reference_page': ref_page, 'is_inherently_major': is_inherently_major}
            return render_template('settings/violations/add_edit_violation.html', form_action_url=url_for('views.add_violation'), violation=form_data_for_template, current_user=current_user, page_title="Add New Violation")
        new_violation = ViolationCatalog(violation_code=code, description=description, type=type_, reference_page=ref_page if ref_page else None, is_inherently_major=is_inherently_major)
        try:
            db.session.add(new_violation); db.session.commit(); flash(f'Violation "{code}" added successfully!', 'success'); return redirect(url_for('views.violation_catalog_list'))
        except Exception as e:
            db.session.rollback(); flash(f'Error adding violation: {str(e)}', 'error')
            form_data_for_template = {'violation_code': code, 'description': description, 'type': type_, 'reference_page': ref_page, 'is_inherently_major': is_inherently_major}
            return render_template('settings/violations/add_edit_violation.html',form_action_url=url_for('views.add_violation'),violation=form_data_for_template,current_user=current_user,page_title="Add New Violation")
    return render_template('settings/violations/add_edit_violation.html', form_action_url=url_for('views.add_violation'), violation=None, current_user=current_user, page_title="Add New Violation")

@views_bp.route('/settings/violations/<int:violation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_violation(violation_id):
    violation_to_edit = ViolationCatalog.query.get_or_404(violation_id)
    if request.method == 'POST':
        description = request.form.get('description', '').strip(); type_ = request.form.get('type'); ref_page = request.form.get('reference_page', '').strip(); is_inherently_major = 'is_inherently_major' in request.form
        errors = []
        if not description: errors.append("Description is required.")
        if type_ not in ['Minor', 'Major']: errors.append("Invalid Violation Type selected.")
        if ref_page and len(ref_page) > 10: errors.append("Reference Page cannot exceed 10 characters.")
        if errors:
            for error in errors: flash(error, 'error')
            return render_template('settings/violations/add_edit_violation.html', form_action_url=url_for('views.edit_violation', violation_id=violation_id), violation=violation_to_edit, current_user=current_user, page_title=f"Edit Violation: {violation_to_edit.violation_code}")
        violation_to_edit.description = description; violation_to_edit.type = type_; violation_to_edit.reference_page = ref_page if ref_page else None; violation_to_edit.is_inherently_major = is_inherently_major
        try:
            db.session.commit(); flash(f'Violation "{violation_to_edit.violation_code}" updated successfully!', 'success'); return redirect(url_for('views.violation_catalog_list'))
        except Exception as e:
            db.session.rollback(); flash(f'Error updating violation: {str(e)}', 'error')
            return render_template('settings/violations/add_edit_violation.html', form_action_url=url_for('views.edit_violation', violation_id=violation_id), violation=violation_to_edit, current_user=current_user, page_title=f"Edit Violation: {violation_to_edit.violation_code}")
    return render_template('settings/violations/add_edit_violation.html', form_action_url=url_for('views.edit_violation', violation_id=violation_id), violation=violation_to_edit, current_user=current_user, page_title=f"Edit Violation: {violation_to_edit.violation_code}")

@views_bp.route('/settings/violations/<int:violation_id>/delete', methods=['POST'])
@login_required
def delete_violation(violation_id):
    violation_to_delete = ViolationCatalog.query.get_or_404(violation_id)
    incident_count = Incident.query.filter_by(violation_id=violation_id).count()
    if incident_count > 0 : 
        flash(f'Cannot delete violation "{violation_to_delete.violation_code}" as it is linked to {incident_count} incident(s).', 'error')
    else:
        try:
            db.session.delete(violation_to_delete); db.session.commit()
            flash(f'Violation "{violation_to_delete.violation_code}" deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Error deleting violation: {str(e)}', 'error')
    return redirect(url_for('views.violation_catalog_list'))

# === USER (STAFF) MANAGEMENT ROUTES ===
@views_bp.route('/settings/users')
@login_required
def user_list():
    users = StaffUser.query.order_by(StaffUser.full_name).all()
    return render_template('settings/users/list.html', users=users, current_user=current_user, page_title="Staff Account Management")

@views_bp.route('/settings/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip(); full_name = request.form.get('full_name', '').strip(); password = request.form.get('password'); confirm_password = request.form.get('confirm_password'); role_str = request.form.get('role')
        errors = []
        if not username: errors.append("Username is required.")
        elif StaffUser.query.filter_by(username=username).first(): errors.append(f"Username '{username}' already exists.")
        if not full_name: errors.append("Full Name is required.")
        if not password: errors.append("Password is required.")
        elif len(password) < 8: errors.append("Password must be at least 8 characters long.")
        if password != confirm_password: errors.append("Passwords do not match.")
        role_enum = None
        if role_str:
            try: role_enum = UserRole[role_str]
            except KeyError: errors.append("Invalid role selected.")
        else: errors.append("Role is required.")
        if errors:
            for error_msg in errors: flash(error_msg, 'error')
        else:
            new_user = StaffUser(username=username, full_name=full_name, role=role_enum, is_active_staff=True)
            new_user.set_password(password)
            try:
                db.session.add(new_user); db.session.flush()
                log_audit("Created User", "StaffUser", new_user.id, f"Created user account '{username}' with role {role_enum.name}")
                db.session.commit()
                flash(f'Staff account "{username}" created successfully!', 'success')
                return redirect(url_for('views.user_list'))
            except Exception as e:
                db.session.rollback(); flash(f'Error creating user account: {str(e)}', 'error')
    return render_template('settings/users/add_edit_user.html', form_action_url=url_for('views.add_user'), user_to_edit=None, roles=UserRole, current_user=current_user, page_title="Add New Staff Account")

@views_bp.route('/settings/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    user_to_edit = StaffUser.query.get_or_404(user_id)
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip(); is_active_staff = 'is_active_staff' in request.form; new_password = request.form.get('new_password'); confirm_new_password = request.form.get('confirm_new_password'); role_str = request.form.get('role')
        errors = []
        if not full_name: errors.append("Full Name is required.")
        role_enum = None
        if role_str:
            try: role_enum = UserRole[role_str]
            except KeyError: errors.append("Invalid role selected.")
        else: errors.append("Role is required.")
        if new_password: 
            if len(new_password) < 8: errors.append("New password must be at least 8 characters long.")
            if new_password != confirm_new_password: errors.append("New passwords do not match.")
        if errors:
            for error_msg in errors: flash(error_msg, 'error')
        else: 
            user_to_edit.full_name = full_name; user_to_edit.is_active_staff = is_active_staff; user_to_edit.role = role_enum
            log_details = f"Edited user '{user_to_edit.username}'. Full Name: {full_name}, Role: {role_enum.name}, Active: {is_active_staff}"
            if new_password: 
                user_to_edit.set_password(new_password)
                flash('Password updated successfully.', 'info') 
                log_details += " (Password Changed)"
            log_audit("Edited User", "StaffUser", user_to_edit.id, log_details)
            try:
                db.session.commit(); flash(f'User "{user_to_edit.username}" details updated successfully!', 'success')
                return redirect(url_for('views.user_list'))
            except Exception as e:
                db.session.rollback(); flash(f'Error updating user: {str(e)}', 'error')
    return render_template('settings/users/add_edit_user.html', form_action_url=url_for('views.edit_user', user_id=user_id), user_to_edit=user_to_edit, roles=UserRole, current_user=current_user, page_title=f"Edit Staff Account: {user_to_edit.username}")

# === REPORTING ROUTES ===
@views_bp.route('/reports') 
@login_required
def reports_page():
    return render_template('reports/reports_overview.html', current_user=current_user, page_title="Reports Overview")

@views_bp.route('/reports/audit_trail')
@login_required
def report_audit_trail():
    page = request.args.get('page', 1, type=int); per_page = 20
    query = AuditLog.query.join(StaffUser, AuditLog.user_id == StaffUser.id).options(joinedload(AuditLog.user)).order_by(AuditLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template('reports/audit_trail.html', pagination=pagination, current_user=current_user, page_title="System Audit Trail")

@views_bp.route('/reports/students_with_offenses')
@login_required
def report_students_with_offenses():
    page = request.args.get('page', 1, type=int); per_page = 15; program_id_filter = request.args.get('program', type=int); year_section_filter = request.args.get('year_section_query', '').strip(); min_offenses_filter = request.args.get('min_offenses', 1, type=int); offense_date_from_str = request.args.get('offense_date_from', '').strip(); offense_date_to_str = request.args.get('offense_date_to', '').strip()
    offense_date_from = None; offense_date_to = None
    if offense_date_from_str:
        try: offense_date_from = datetime.strptime(offense_date_from_str, '%Y-%m-%d')
        except ValueError: flash('Invalid "Offense Date From" format. Please use YYYY-MM-DD.', 'error')
    if offense_date_to_str:
        try: offense_date_to = datetime.strptime(offense_date_to_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError: flash('Invalid "Offense Date To" format. Please use YYYY-MM-DD.', 'error')
    incident_counts_subquery = db.session.query(Incident.student_id, func.count(Incident.id).label('total_incidents_filtered'), func.sum(db.case((and_(ViolationCatalog.type == 'Minor', Incident.is_escalated_to_major == False), 1), else_=0)).label('minor_offenses_filtered'), func.sum(db.case((or_(ViolationCatalog.type == 'Major', Incident.is_escalated_to_major == True), 1), else_=0)).label('major_offenses_filtered')).join(ViolationCatalog, Incident.violation_id == ViolationCatalog.id)
    if offense_date_from: incident_counts_subquery = incident_counts_subquery.filter(Incident.date_committed >= offense_date_from)
    if offense_date_to: incident_counts_subquery = incident_counts_subquery.filter(Incident.date_committed < offense_date_to)
    incident_counts_subquery = incident_counts_subquery.group_by(Incident.student_id).subquery()
    query = db.session.query(Student, incident_counts_subquery.c.total_incidents_filtered, incident_counts_subquery.c.minor_offenses_filtered, incident_counts_subquery.c.major_offenses_filtered).join(incident_counts_subquery, Student.id == incident_counts_subquery.c.student_id).options(joinedload(Student.program))
    if program_id_filter: query = query.filter(Student.program_id == program_id_filter)
    if year_section_filter: query = query.filter(Student.year_section.ilike(f"%{year_section_filter}%"))
    if min_offenses_filter > 0: query = query.filter(incident_counts_subquery.c.total_incidents_filtered >= min_offenses_filter)
    query = query.order_by(Student.last_name, Student.first_name)
    pagination_obj = query.paginate(page=page, per_page=per_page, error_out=False)
    students_report_data = [{'student': student_obj, 'total_incidents': total or 0, 'minor_offenses': minor or 0, 'major_offenses': major or 0} for student_obj, total, minor, major in pagination_obj.items]
    programs_for_filter = Program.query.order_by(Program.program_name).all()
    return render_template('reports/students_with_offenses.html', students_report_data=students_report_data, pagination=pagination_obj, programs_for_filter=programs_for_filter, current_user=current_user, page_title="Student Offense Report")

@views_bp.route('/reports/violation_frequency')
@login_required
def report_violation_frequency():
    date_from_str = request.args.get('date_from', '').strip(); date_to_str = request.args.get('date_to', '').strip(); violation_type_filter = request.args.get('violation_type', '').strip()
    date_from = None
    if date_from_str:
        try: date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
        except ValueError: flash('Invalid "Incidents From" date format. Please use YYYY-MM-DD.', 'error')
    date_to = None
    if date_to_str:
        try: date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1) 
        except ValueError: flash('Invalid "Incidents To" date format. Please use YYYY-MM-DD.', 'error')
    query = db.session.query(ViolationCatalog.violation_code, ViolationCatalog.description, ViolationCatalog.type, func.count(Incident.id).label('frequency_count')).join(Incident, ViolationCatalog.id == Incident.violation_id)
    if date_from: query = query.filter(Incident.date_committed >= date_from)
    if date_to: query = query.filter(Incident.date_committed < date_to)
    if violation_type_filter: query = query.filter(ViolationCatalog.type == violation_type_filter)
    violation_report_data_query = query.group_by(ViolationCatalog.id, ViolationCatalog.violation_code, ViolationCatalog.description, ViolationCatalog.type).order_by(func.count(Incident.id).desc(), ViolationCatalog.violation_code).all()
    violation_report_data = [{'code': item[0], 'description': item[1], 'type': item[2], 'count': item[3]} for item in violation_report_data_query]
    return render_template('reports/violation_frequency.html', violation_report_data=violation_report_data, current_user=current_user, page_title="Violation Frequency Report")

@views_bp.route('/reports/sanction_monitoring')
@login_required
def report_sanction_monitoring():
    page = request.args.get('page', 1, type=int); per_page = 15; student_query_str = request.args.get('student_query', '').strip(); sanction_type_query = request.args.get('sanction_type_query', '').strip(); completion_status_filter = request.args.get('completion_status', '').strip(); due_date_from_str = request.args.get('due_date_from', '').strip()
    query = SanctionLog.query.join(Incident, SanctionLog.incident_id == Incident.id).join(Student, Incident.student_id == Student.id).options(joinedload(SanctionLog.incident).joinedload(Incident.student).joinedload(Student.program), joinedload(SanctionLog.incident).joinedload(Incident.violation))
    if student_query_str:
        search_term = f"%{student_query_str}%"
        query = query.filter(or_(Student.first_name.ilike(search_term), Student.last_name.ilike(search_term), (Student.first_name + " " + Student.last_name).ilike(search_term), Student.student_number.ilike(search_term)))
    if sanction_type_query: query = query.filter(SanctionLog.sanction_type.ilike(f"%{sanction_type_query}%"))
    today_date = datetime.utcnow().date() 
    if completion_status_filter:
        if completion_status_filter == 'Pending': query = query.filter(SanctionLog.completion_date == None, (SanctionLog.due_date == None) | (SanctionLog.due_date >= today_date))
        elif completion_status_filter == 'Completed': query = query.filter(SanctionLog.completion_date != None)
        elif completion_status_filter == 'Overdue': query = query.filter(SanctionLog.completion_date == None, SanctionLog.due_date != None, SanctionLog.due_date < today_date)
    if due_date_from_str:
        try: due_date_from = datetime.strptime(due_date_from_str, '%Y-%m-%d').date(); query = query.filter(SanctionLog.due_date >= due_date_from)
        except ValueError: flash('Invalid "Due Date From" format. Please use YYYY-MM-DD.', 'error')
    query = query.order_by(db.func.isnull(SanctionLog.due_date), SanctionLog.due_date.asc(), SanctionLog.date_assigned.desc())
    pagination_obj = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template('reports/sanction_monitoring.html', pagination=pagination_obj, current_user=current_user, today=today_date, page_title="Sanction Monitoring Report")

# --- SETTINGS OVERVIEW PAGE ---
@views_bp.route('/settings') 
@login_required
def settings_page():
    return render_template('settings/settings_overview.html', current_user=current_user, page_title="System Settings")

## In mainsub/views.py

@views_bp.route('/students/import', methods=['GET', 'POST'])
@login_required
def import_students():
    if request.method == 'POST':
        if 'student_file' not in request.files:
            flash('No file part in the request.', 'error')
            return redirect(request.url)
        
        file = request.files['student_file']
        if file.filename == '':
            flash('No file selected for uploading.', 'error')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            try:
                base_name = os.path.splitext(filename)[0]
                
                last_space = base_name.rfind(' ')
                last_underscore = base_name.rfind('_')
                
                separator_index = max(last_space, last_underscore)
                
                if separator_index == -1:
                    raise ValueError("Filename must contain a space or underscore between program code and section.")

                program_code_from_file = base_name[:separator_index].strip().upper()
                year_section_str = base_name[separator_index + 1:].strip().upper()

                if not program_code_from_file or not year_section_str:
                     raise ValueError("Filename format is invalid. Ensure it is 'programcode yearsection'.")

                program = Program.query.filter(func.upper(Program.program_code) == program_code_from_file).first()
                
                if not program:
                    flash(f"Program with code '{program_code_from_file}' not found in the database. Please check the filename.", 'error')
                    return redirect(request.url)

            except Exception as e:
                flash(f"Invalid filename format. {str(e)}", 'error')
                return redirect(request.url)

            try:
                # --- START: THIS IS THE FINAL, CORRECTED LINE ---
                # Your headers are on Row 8, which is index 7 for pandas.
                df = pd.read_excel(file, header=7)
                # --- END OF CORRECTION ---

                # Clean up any extra spaces from the column names, just in case
                df.columns = df.columns.str.strip()

                required_cols = {
                    'Student No.': 'student_number',
                    'Surname': 'last_name',
                    'First Name': 'first_name',
                    'Middle Name': 'middle_name',
                    'Contact Number': 'contact_info_phone',
                    'E-mail Address': 'contact_info_email'
                }

                if not all(col in df.columns for col in required_cols.keys()):
                    flash('The uploaded file is missing required columns. Please use the template.', 'error')
                    return redirect(request.url)

                added_count = 0
                updated_count = 0
                skipped_count = 0
                
                for index, row in df.iterrows():
                    if pd.isna(row['Student No.']):
                        skipped_count += 1
                        continue
                    student_no = str(row['Student No.']).strip()
                    if not student_no:
                        skipped_count += 1
                        continue

                    student = Student.query.filter_by(student_number=student_no).first()
                    
                    if student:
                        student.first_name = str(row['First Name']).strip()
                        student.last_name = str(row['Surname']).strip()
                        student.middle_name = str(row['Middle Name']).strip() if pd.notna(row['Middle Name']) else None
                        student.program_id = program.id
                        student.year_section = year_section_str
                        student.contact_info_phone = str(row['Contact Number']).strip() if pd.notna(row['Contact Number']) else None
                        student.contact_info_email = str(row['E-mail Address']).strip() if pd.notna(row['E-mail Address']) else None
                        updated_count += 1
                    else:
                        new_student = Student(
                            student_number=student_no,
                            first_name=str(row['First Name']).strip(),
                            last_name=str(row['Surname']).strip(),
                            middle_name=str(row['Middle Name']).strip() if pd.notna(row['Middle Name']) else None,
                            program_id=program.id,
                            year_section=year_section_str,
                            contact_info_phone=str(row['Contact Number']).strip() if pd.notna(row['Contact Number']) else None,
                            contact_info_email=str(row['E-mail Address']).strip() if pd.notna(row['E-mail Address']) else None,
                        )
                        db.session.add(new_student)
                        added_count += 1
                
                db.session.commit()
                flash(f"Import successful! Added: {added_count}, Updated: {updated_count}, Skipped rows: {skipped_count}.", 'success')
                return redirect(url_for('views.student_list'))

            except Exception as e:
                db.session.rollback()
                flash(f"An error occurred while processing the file: {str(e)}", 'error')
                return redirect(request.url)

        else:
            flash('Invalid file type. Please upload an .xlsx file.', 'error')
            return redirect(request.url)
    
    return render_template('students/import_students.html')