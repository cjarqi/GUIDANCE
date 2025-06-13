# GUIDANCE/mainsub/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length

class FileGrievanceForm(FlaskForm):
    student_id = SelectField('Student Complainant', coerce=int, validators=[DataRequired()])
    respondent_name = StringField('Respondent Full Name', validators=[DataRequired(), Length(max=150)])
    respondent_type = SelectField('Respondent Type', 
                                  choices=[
                                      ('Fellow Student', 'Fellow Student'),
                                      ('Faculty Member', 'Faculty Member'),
                                      ('Administrator', 'Administrator'),
                                      ('Support/Employee Staff', 'Support/Employee Staff')
                                  ],
                                  validators=[DataRequired()])
    initial_complaint = TextAreaField('Details of Complaint / Grievance', validators=[DataRequired(), Length(min=20)])
    submit = SubmitField('File Grievance')

class GrievanceUpdateForm(FlaskForm):
    update_details = TextAreaField('Update Details / Resolution Notes', validators=[DataRequired(), Length(min=10)])
    new_status = SelectField('Set New Status', validators=[DataRequired()])
    submit = SubmitField('Add Update')