"""School logo helpers shared by the result-card / result-sheet PDFs.

The logo shown on a PDF must always be the one the school uploaded in
Settings (stored in the per-school data folder), never a fixed product image.
When the school has not uploaded a logo, no logo is drawn.
"""
import os


def school_logo_path(root_path=None):
    """Absolute path of the school's uploaded logo, or '' when none is set."""
    from app.services.id_documents import school_branding

    if root_path is None:
        try:
            from flask import current_app
            root_path = current_app.root_path
        except Exception:  # no app context
            root_path = None
    if not root_path:
        return ''
    path = school_branding(root_path).get('logo_path') or ''
    return path if path and os.path.isfile(path) else ''


def logo_flowable(path, max_w=60, max_h=60):
    """Aspect-correct reportlab Image for the logo, or None if unusable."""
    if not path:
        return None
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.platypus import Image

        width, height = ImageReader(path).getSize()
        if not width or not height:
            return None
        scale = min(max_w / float(width), max_h / float(height))
        return Image(path, width=width * scale, height=height * scale)
    except Exception:
        return None
