import io
import os
import unittest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('INITIAL_ADMIN_USERNAME', 'admin')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'adminpass123')

from reportlab.lib.units import mm

from app.services import id_documents


def _person(role_pill=None):
    return {
        'name': 'Test Person', 'badge': 'STUDENT ID', 'role_label': 'Student',
        'role_pill': role_pill, 'qr': 'TEST-1',
        'rows': [('Class', '5'), ('Roll', '1'), ('Phone', '0300')],
    }


class IdCardSizeTests(unittest.TestCase):
    def test_card_is_cr80_85_6_by_54_mm(self):
        self.assertAlmostEqual(id_documents.CARD_W / mm, 85.6, places=3)
        self.assertAlmostEqual(id_documents.CARD_H / mm, 54.0, places=3)

    def test_both_styles_build_a_pdf(self):
        school = {'name': 'School', 'tagline': '', 'address': 'Addr',
                  'phone': '0300', 'email': '', 'logo_path': ''}
        for style in id_documents.CARD_STYLES:
            for pill in (None, 'Teacher'):
                out = id_documents.build_id_cards_pdf(
                    [_person(pill)], school, '2026-2027', style=style)
                self.assertTrue(out.read().startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
