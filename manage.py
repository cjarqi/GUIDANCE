# GUIDANCE/manage.py

import os
from mainsub import create_app, db
from mainsub.models import Program, Student, ViolationCatalog, StaffUser, Incident, SanctionLog, UserRole
from datetime import datetime, timedelta

# Create an app instance for the CLI
# This will correctly load the environment variables from Render
app = create_app()

@app.cli.command("seed_db")
def seed_db():
    """Seeds the database with initial data."""
    print("--- Starting Data Seeding ---")

    # Check if the superadmin user already exists to prevent errors on re-runs
    if StaffUser.query.filter_by(username="superadmin").first():
        print("Superadmin user already exists. Skipping user creation.")
    else:
        print("Creating superadmin user...")
        superadmin = StaffUser(
            username="superadmin", 
            email="aikolykm04@gmail.com",
            full_name="Guidance Counselor", 
            role=UserRole.COUNSELOR
        )
        superadmin.set_password("guidance") 
        db.session.add(superadmin)
        print("Superadmin user created.")

    # You can add more checks for programs, etc., in the same way.
    # For now, we'll just create the user.
    # Add other seeding logic from your seed_data.py here if needed.
    
    # --- Example: Add a Program if it doesn't exist ---
    if not Program.query.filter_by(program_code="BSCS").first():
        print("Creating BSCS Program...")
        prog = Program(program_name="Bachelor of Science in Computer Science", program_code="BSCS")
        db.session.add(prog)
        print("BSCS Program created.")

    try:
        db.session.commit()
        print("--- Data Seeding Finished Successfully ---")
    except Exception as e:
        db.session.rollback()
        print(f"--- Error during seeding: {e} ---")