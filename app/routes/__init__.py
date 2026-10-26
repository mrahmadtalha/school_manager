from flask import Blueprint

main = Blueprint('main', __name__)

from app.routes import (
    dashboard,
    executive,
    students,
    promotions,
    teachers,
    classes,
    timetable_sheet,
    attendance,
    examinations,
    term_exams,
    fees,
    expenses,
    payroll,
    financials,
    reports,
    settings,
    documents,
    users,
    audit,
    portal,
    license,
    other_income,
    inventory,
    assistant,
    admission_fees,
    qr_attendance,
)