"""Issued ID cards and certificates (Phase 5).

One row per *issue* of a student's ID card or certificate.  It is what lets
the software tell a first issue from a duplicate, and it links to the fee
receipt (an ``OtherIncome`` row) when a fee was taken.  Rows are never
deleted: a wrong issue is voided with a reason.
"""
from datetime import datetime

from app.database import db

DOC_ID_CARD = 'id_card'
DOC_CERTIFICATE = 'certificate'
DOC_KINDS = (DOC_ID_CARD, DOC_CERTIFICATE)


class IssuedDocument(db.Model):
    __tablename__ = 'issued_documents'

    id = db.Column(db.Integer, primary_key=True)
    doc_kind = db.Column(db.String(20), nullable=False, index=True)
    cert_type = db.Column(db.String(20), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           nullable=False, index=True)
    session = db.Column(db.String(50), nullable=True)
    issue_date = db.Column(db.Date, nullable=False)
    remarks = db.Column(db.String(200), nullable=True)

    is_duplicate = db.Column(db.Boolean, nullable=False, default=False)
    # Fee taken for this issue (paisa); 0 = free.  The money itself lives in
    # the linked Other Income row, which is what the reports count.
    fee_paisa = db.Column(db.Integer, nullable=False, default=0)
    income_id = db.Column(db.Integer, db.ForeignKey('other_income.id'),
                          nullable=True, index=True)

    is_void = db.Column(db.Boolean, nullable=False, default=False)
    void_reason = db.Column(db.String(255), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by_name = db.Column(db.String(80), nullable=True)

    created_by_id = db.Column(db.Integer, nullable=True)
    created_by_name = db.Column(db.String(80), nullable=True, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship('StudentModel', lazy=True)
    income = db.relationship('OtherIncome', lazy=True)

    @property
    def is_effective(self):
        """Counts as issued: not voided, and its fee receipt not voided."""
        if self.is_void:
            return False
        return not (self.income is not None and self.income.is_void)

    def __repr__(self):
        return f'<IssuedDocument {self.id} {self.doc_kind} student={self.student_id}>'
