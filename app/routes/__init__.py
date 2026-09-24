from flask import Blueprint

main = Blueprint('main', __name__)

from app.routes import (
    dashboard,
    students,
    teachers,
    classes,
    attendance,
    examinations,
    fees,
    reports,
    settings,
)
