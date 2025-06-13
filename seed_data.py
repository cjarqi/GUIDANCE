# GUIDANCE/seed_data.py
from mainsub import db, create_app
from mainsub.models import Program, Student, ViolationCatalog, StaffUser, Incident, SanctionLog, UserRole
from datetime import datetime, timedelta

app = create_app()

with app.app_context():
    print("--- Starting Data Seeding ---")

    print("Clearing all data from all tables...")
    try:
        # Clear tables in order to respect foreign keys
        SanctionLog.query.delete()
        Incident.query.delete()
        Student.query.delete()
        Program.query.delete()
        ViolationCatalog.query.delete()
        StaffUser.query.delete() 
        db.session.commit()
        print("All tables cleared successfully.")
    except Exception as e:
        db.session.rollback()
        print(f"Error clearing tables: {e}. Please ensure DB is empty or drop/recreate.")
        exit() # Exit if we can't clear the database properly

    # --- Step 1: Create Programs ---
    print("Creating Programs...")
    programs_data = [
        {"name": "Bachelor of Science in Computer Science", "code": "BSCS"},
        {"name": "Bachelor of Science in Management Accountancy", "code": "BSMA"},
        {"name": "Bachelor of Science in Criminology", "code": "BSCrim"},
        {"name": "Bachelor of Public Administration", "code": "BPA"}
    ]
    created_programs = {}
    for p_data in programs_data:
        prog = Program(program_name=p_data["name"], program_code=p_data["code"])
        db.session.add(prog)
    db.session.commit()
    for p_data in programs_data:
        created_programs[p_data["code"]] = Program.query.filter_by(program_code=p_data["code"]).first()
    print("Programs created.")

    # --- Step 2: Create superadmin user ---
    print("Creating superadmin user...")
    superadmin = StaffUser(
        username="superadmin", 
        email="aikolykm04@gmail.com",
        full_name="Guidance Counselor", 
        role=UserRole.COUNSELOR
    )
    superadmin.set_password("guidance") 
    db.session.add(superadmin)
    db.session.commit()
    print("Superadmin created.")

    # --- Step 3: Create Students ---
    print("Creating Students...")
    students_data = [
        {"number": "P20230001", "first": "John", "last": "Doe", "year_section": "1A", "prog_code": "BSCS"},
        {"number": "P20230002", "first": "Jane", "last": "Smith", "year_section": "2B", "prog_code": "BSMA"},
        {"number": "P20220003", "first": "Mike", "last": "Brown", "year_section": "3C", "prog_code": "BSCrim"},
        {"number": "P20230004", "first": "Lisa", "last": "Ray", "year_section": "1A", "prog_code": "BPA"},
        {"number": "P20210005", "first": "Kevin", "last": "Lee", "year_section": "4D", "prog_code": "BSCS"},
        {"number": "P20240006", "first": "Christian", "last": "Arquillo", "year_section": "1B", "prog_code": "BSCS"},
    ]
    for s_data in students_data:
        program_object = created_programs.get(s_data["prog_code"])
        if program_object:
            student = Student(student_number=s_data["number"], first_name=s_data["first"], last_name=s_data["last"], year_section=s_data["year_section"].upper(), program_id=program_object.id)
            db.session.add(student)
    db.session.commit()
    print("Students created.")

    # --- Step 4: Create FULL Violation Catalog from Handbook ---
    print("Creating FULL Violation Catalog...")
    violations_data = [
        {"code":"M01", "desc":"Behavior considered unbecoming of a Christian adult.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M01a", "desc":"Disturbing classes without valid reasons.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M01b", "desc":"Shouting at the corridor.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M01c", "desc":"Using cell phone during classes and college programs/ceremonies.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M01d", "desc":"Sitting on the table or the parapets.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M01e", "desc":"Wearing a cap inside the classroom and offices.", "type":"Minor", "ref":"p.1", "is_major":False},
        {"code":"M02", "desc":"Entering a class or breaking into any College function without permission.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M03", "desc":"Charging gadgets in the classroom or any other places in the campus.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M04", "desc":"Loitering near classrooms during class sessions.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M05", "desc":"Unauthorized use of chalk and board.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M06", "desc":"Proselytizing.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M07", "desc":"Eating inside the classroom.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M08", "desc":"Playing cards.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M09", "desc":"Using someone else's library card/school ID.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M010", "desc":"Wearing earrings for boys.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M011", "desc":"Blonde hair.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M012", "desc":"Long hair for boys.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M013", "desc":"Spitting.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M014", "desc":"Not switching off the aircon, lights and electric fan.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M015", "desc":"Not using the comfort room properly.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M016", "desc":"Violation of dress code during wash days.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M017", "desc":"Defacing, mutilating, or removing posters within valid period of posting.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M018", "desc":"Violation of usual classroom policies and procedures as well as those set by the teachers.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M019", "desc":"Posting of announcements without prior approval of the Office of the Head/Director/Coordinator of Student Affairs.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M020", "desc":"Unauthorized use of school facilities by non-recognized organization, groups of individuals.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"M021", "desc":"Other minor offenses as determined and approved by the BOT.", "type":"Minor", "ref":"p.2", "is_major":False},
        {"code":"MJ01", "desc":"Commission of a third minor offense.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ02", "desc":"Acts of Gross dishonesty; Giving false statement to obstruct Justice.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ03", "desc":"Any form of bullying.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ04", "desc":"Not wearing the prescribed students uniform and I.D.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ05", "desc":"Any form of discrimination.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ06", "desc":"Physical/Mental/Verbal Abuse.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ07", "desc":"Oral Defamation.", "type":"Major", "ref":"p.2", "is_major":True},
        {"code":"MJ08", "desc":"Posting any pictures, messages, videos, text, and others that will violate one's basic rights to privacy, honor and respect.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ09", "desc":"Posting in any social media that violates school policies and government laws.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ10", "desc":"Unauthorized entry to offices and opening of drawers, cabinets, etc.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ11", "desc":"Acts of gross disrespect which tend to insult or subject to public ridicule or contempt any member of the community.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ12", "desc":"Defaming in words/deeds such as thru text messaging and the internet, as well as unjust vexations.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ13", "desc":"Using or lending someone else's ID card, registration form, etc.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ14", "desc":"Unauthorized collection or extortion of money.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ15", "desc":"Cheating in any form.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ15f", "desc":"Passing as one's own work any assigned report, term paper, etc.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ16", "desc":"Habitual disregard or repeated willful violations of established policies.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ17", "desc":"Deliberate disruption of the academic function or any College activity.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ18", "desc":"Assault upon any person within the premises of the College.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ19", "desc":"Threatening another with infliction of harm.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ20", "desc":"Acts that malign the good name and reputation of the school.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ21", "desc":"Acts of subversion or insurgency.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ22", "desc":"Violation of conditions of being under probation.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ23", "desc":"Commission of a second major offense.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ24", "desc":"Brawls on campus or at any school function.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ25", "desc":"Inflicting physical injuries upon another within the campus.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ26", "desc":"Any similar or analogous acts to any major offenses.", "type":"Major", "ref":"p.3", "is_major":True},
        {"code":"MJ27", "desc":"Other major offenses as determined and approved by the BOT.", "type":"Major", "ref":"p.3", "is_major":True},
    ]
    for v_data in violations_data:
        v = ViolationCatalog(violation_code=v_data["code"], description=v_data["desc"], type=v_data["type"], is_inherently_major=v_data.get("is_major", False), reference_page=v_data.get("ref"))
        db.session.add(v)
    db.session.commit()
    print("Violations created.")

    print("--- Data Seeding Finished ---")