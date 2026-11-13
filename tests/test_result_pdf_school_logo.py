"""Result PDFs must carry the school's own uploaded logo.

Before this fix the report cards, professional result cards and the class
result sheet always drew the product's ``static/logo.png``, whatever logo the
school had uploaded in Settings; term-exam result cards and tabulation sheets
drew no logo at all.

Covers:
- pdf_logo.school_logo_path(): '' without an upload, the uploaded file with one,
  never the product's static logo
- pdf_logo.logo_flowable(): aspect-correct sizing, None for missing/broken files
- Every result PDF embeds the uploaded logo (and not the product logo)
- Every result PDF draws no logo when the school has not uploaded one
- Result cards stay single-page with a logo
"""

import os
import re
from datetime import date

import pytest
from PIL import Image as PILImage

from app.database import db
from app.models import (SchoolSettings, StudentMarkModel, SubjectModel,
                        TermExam, TestModel)

# A size no product asset uses, so the PDF's image dictionary identifies it.
LOGO_SIZE = (37, 23)
STATIC_LOGO = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'logo.png')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_logo(path, size=LOGO_SIZE, color=(200, 30, 30)):
    PILImage.new('RGB', size, color).save(path)


def _set_school_logo(app, tmp_path):
    """Upload a logo the way Settings does: file in DATA_DIR/uploads + filename."""
    app.config['DATA_DIR'] = str(tmp_path)
    uploads = tmp_path / 'uploads'
    uploads.mkdir(exist_ok=True)
    _make_logo(str(uploads / 'logo.png'))
    school = SchoolSettings.query.first() or SchoolSettings()
    school.school_name = 'Logo Test School'
    school.logo_filename = 'logo.png'
    db.session.add(school)
    db.session.commit()


def _clear_school_logo(app, tmp_path):
    app.config['DATA_DIR'] = str(tmp_path)
    school = SchoolSettings.query.first() or SchoolSettings()
    school.school_name = 'Logo Test School'
    school.logo_filename = ''
    db.session.add(school)
    db.session.commit()


def _image_sizes(pdf_bytes):
    """(width, height) of every image XObject embedded in the PDF."""
    sizes = []
    for match in re.finditer(rb'/Subtype\s*/Image', pdf_bytes):
        window = pdf_bytes[max(0, match.start() - 400):match.end() + 400]
        w = re.search(rb'/Width\s+(\d+)', window)
        h = re.search(rb'/Height\s+(\d+)', window)
        if w and h:
            sizes.append((int(w.group(1)), int(h.group(1))))
    return sizes


def _page_count(pdf_bytes):
    return len(re.findall(rb'/Type\s*/Page(?![s\w])', pdf_bytes))


def _add_marks(class_id, student_ids, term_exam_id=None, test_type='Monthly'):
    subject = SubjectModel.query.filter_by(class_id=class_id).first()
    test = TestModel(test_title='Logo Test', test_date=date(2026, 10, 1),
                     test_type=test_type, class_id=class_id,
                     subject_id=subject.id, total_marks=100,
                     term_exam_id=term_exam_id)
    db.session.add(test)
    db.session.flush()
    for sid in student_ids:
        db.session.add(StudentMarkModel(test_id=test.id, student_id=sid,
                                        marks_obtained=82, percentage=82.0,
                                        grade='A'))
    db.session.commit()
    return test


def _make_term_exam(class_id, student_ids):
    exam = TermExam(name='Mid Term 2026', class_id=class_id, exam_type='Mid-Term',
                    session_label='2026-27', start_date=date(2026, 10, 1),
                    end_date=date(2026, 10, 5), announce_date=date(2026, 10, 10))
    db.session.add(exam)
    db.session.flush()
    _add_marks(class_id, student_ids, term_exam_id=exam.id, test_type='Mid-Term')
    return exam


def _pdf_urls(app, seed):
    """Every result PDF endpoint, as {label: url}, with data seeded behind it."""
    cid = seed['class_id']
    students = [seed['student_id'], seed['other_student_id']]
    _add_marks(cid, students)
    exam = _make_term_exam(cid, students)
    sid = seed['student_id']
    return {
        'classic_card': '/reports/student/%d/pdf?class_id=%d&card_style=classic' % (sid, cid),
        'professional_card': '/reports/student/%d/pdf?class_id=%d&card_style=professional' % (sid, cid),
        'class_result_sheet': '/reports/class-results/pdf-class?class_id=%d' % cid,
        'term_result_card': '/examinations/%d/results/%d.pdf' % (exam.id, sid),
        'term_result_cards_all': '/examinations/%d/results/pdf-all' % exam.id,
        'term_tabulation': '/examinations/%d/tabulation/export.pdf' % exam.id,
    }


PDF_LABELS = ['classic_card', 'professional_card', 'class_result_sheet',
              'term_result_card', 'term_result_cards_all', 'term_tabulation']


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestSchoolLogoPath:
    def test_empty_when_school_has_no_logo(self, app, tmp_path):
        from app.services.pdf_logo import school_logo_path
        _clear_school_logo(app, tmp_path)
        # The product's static logo exists, but it is not the school's.
        assert os.path.isfile(STATIC_LOGO)
        assert school_logo_path(app.root_path) == ''

    def test_returns_uploaded_logo(self, app, tmp_path):
        from app.services.pdf_logo import school_logo_path
        _set_school_logo(app, tmp_path)
        assert school_logo_path(app.root_path) == str(tmp_path / 'uploads' / 'logo.png')

    def test_uses_current_app_root_when_not_given(self, app, tmp_path):
        from app.services.pdf_logo import school_logo_path
        _set_school_logo(app, tmp_path)
        assert school_logo_path() == str(tmp_path / 'uploads' / 'logo.png')

    def test_missing_file_gives_empty_path(self, app, tmp_path):
        """logo_filename set but the file exists nowhere: no logo, no crash."""
        from app.services.pdf_logo import school_logo_path
        _set_school_logo(app, tmp_path)
        school = SchoolSettings.query.first()
        school.logo_filename = 'deleted-school-logo.png'
        db.session.commit()
        assert school_logo_path(app.root_path) == ''

    def test_matches_the_logo_the_app_shows(self, app, tmp_path):
        """PDFs resolve the logo exactly like the sidebar's /brand-logo."""
        from app.services.pdf_logo import school_logo_path
        _set_school_logo(app, tmp_path)
        client = app.test_client()
        from tests.conftest import ADMIN_PASSWORD, login
        login(client, 'admin', ADMIN_PASSWORD)
        shown = client.get('/brand-logo')
        assert shown.status_code == 200
        with open(school_logo_path(app.root_path), 'rb') as handle:
            assert shown.data == handle.read()

    def test_replaced_logo_is_picked_up(self, app, tmp_path):
        """Uploading a new logo changes what the PDFs use (no stale cache)."""
        from app.services.pdf_logo import school_logo_path
        _set_school_logo(app, tmp_path)
        school = SchoolSettings.query.first()
        _make_logo(str(tmp_path / 'uploads' / 'logo.jpg'))
        school.logo_filename = 'logo.jpg'
        db.session.commit()
        assert school_logo_path(app.root_path).endswith('logo.jpg')


class TestLogoFlowable:
    def test_none_for_empty_path(self):
        from app.services.pdf_logo import logo_flowable
        assert logo_flowable('') is None
        assert logo_flowable(None) is None

    def test_none_for_missing_file(self, tmp_path):
        from app.services.pdf_logo import logo_flowable
        assert logo_flowable(str(tmp_path / 'nope.png')) is None

    def test_none_for_corrupt_file(self, tmp_path):
        from app.services.pdf_logo import logo_flowable
        bad = tmp_path / 'bad.png'
        bad.write_bytes(b'not an image')
        assert logo_flowable(str(bad)) is None

    def test_aspect_ratio_preserved_wide(self, tmp_path):
        from app.services.pdf_logo import logo_flowable
        path = tmp_path / 'wide.png'
        _make_logo(str(path), size=(200, 100))
        img = logo_flowable(str(path), 60, 60)
        assert img.drawWidth == pytest.approx(60)
        assert img.drawHeight == pytest.approx(30)

    def test_aspect_ratio_preserved_tall(self, tmp_path):
        from app.services.pdf_logo import logo_flowable
        path = tmp_path / 'tall.png'
        _make_logo(str(path), size=(100, 400))
        img = logo_flowable(str(path), 60, 60)
        assert img.drawWidth == pytest.approx(15)
        assert img.drawHeight == pytest.approx(60)

    def test_wide_product_logo_is_not_squashed(self):
        """The old code forced every logo into a square, distorting wide ones."""
        from app.services.pdf_logo import logo_flowable
        img = logo_flowable(STATIC_LOGO, 54, 54)
        assert img.drawWidth > img.drawHeight


# ---------------------------------------------------------------------------
# PDFs with the school's logo
# ---------------------------------------------------------------------------

class TestResultPdfsUseSchoolLogo:
    @pytest.mark.parametrize('label', PDF_LABELS)
    def test_pdf_embeds_uploaded_logo(self, admin_client, app, seed, tmp_path, label):
        _set_school_logo(app, tmp_path)
        url = _pdf_urls(app, seed)[label]
        r = admin_client.get(url)
        assert r.status_code == 200, label
        assert r.mimetype == 'application/pdf', label
        sizes = _image_sizes(r.data)
        # Aspect ratio kept: 37x23 source stays 37x23 pixels in the PDF.
        assert LOGO_SIZE in sizes, '%s: school logo missing, images=%s' % (label, sizes)

    @pytest.mark.parametrize('label', PDF_LABELS)
    def test_pdf_never_embeds_product_logo(self, admin_client, app, seed, tmp_path, label):
        _set_school_logo(app, tmp_path)
        url = _pdf_urls(app, seed)[label]
        r = admin_client.get(url)
        product_size = PILImage.open(STATIC_LOGO).size
        assert product_size not in _image_sizes(r.data), label

    @pytest.mark.parametrize('label', PDF_LABELS)
    def test_pdf_has_no_logo_when_school_has_none(self, admin_client, app, seed,
                                                  tmp_path, label):
        """No upload means no logo - not the product's default image."""
        _clear_school_logo(app, tmp_path)
        url = _pdf_urls(app, seed)[label]
        r = admin_client.get(url)
        assert r.status_code == 200, label
        assert _image_sizes(r.data) == [], label

    def test_logo_follows_replacement(self, admin_client, app, seed, tmp_path):
        """After the school swaps its logo, the PDF shows the new one."""
        _set_school_logo(app, tmp_path)
        urls = _pdf_urls(app, seed)
        assert LOGO_SIZE in _image_sizes(admin_client.get(urls['classic_card']).data)

        new_size = (51, 29)
        _make_logo(str(tmp_path / 'uploads' / 'logo.png'), size=new_size,
                   color=(10, 120, 200))
        sizes = _image_sizes(admin_client.get(urls['classic_card']).data)
        assert new_size in sizes
        assert LOGO_SIZE not in sizes

    def test_broken_logo_file_does_not_break_pdf(self, admin_client, app, seed, tmp_path):
        """A corrupt upload must never turn result cards into a 500."""
        _set_school_logo(app, tmp_path)
        (tmp_path / 'uploads' / 'logo.png').write_bytes(b'corrupt')
        urls = _pdf_urls(app, seed)
        for label in PDF_LABELS:
            r = admin_client.get(urls[label])
            assert r.status_code == 200, label
            assert _image_sizes(r.data) == [], label


class TestLayoutWithLogo:
    @pytest.mark.parametrize('label', ['classic_card', 'professional_card',
                                       'term_result_card'])
    def test_single_card_stays_on_one_page(self, admin_client, app, seed, tmp_path, label):
        _set_school_logo(app, tmp_path)
        r = admin_client.get(_pdf_urls(app, seed)[label])
        assert _page_count(r.data) == 1, label

    def test_all_term_cards_one_page_per_student(self, admin_client, app, seed, tmp_path):
        """Two students -> two pages; the logo must not spill a card over."""
        _set_school_logo(app, tmp_path)
        r = admin_client.get(_pdf_urls(app, seed)['term_result_cards_all'])
        assert _page_count(r.data) == 2

    def test_logo_drawn_once_per_term_card(self, admin_client, app, seed, tmp_path):
        _set_school_logo(app, tmp_path)
        r = admin_client.get(_pdf_urls(app, seed)['term_result_cards_all'])
        # reportlab reuses one XObject for an identical image file.
        assert LOGO_SIZE in _image_sizes(r.data)

    def test_class_sheet_stays_single_page(self, admin_client, app, seed, tmp_path):
        _set_school_logo(app, tmp_path)
        r = admin_client.get(_pdf_urls(app, seed)['class_result_sheet'])
        assert _page_count(r.data) == 1
