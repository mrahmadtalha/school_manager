"""Optional profile pictures for students and teachers.

Photos are validated, normalised to a JPEG (max 600 px) and stored on disk in
``<instance>/uploads/<kind>/``.  Only the generated file name is kept in the
database (``photo_filename``).  Every function is safe to call when there is no
photo: it simply returns ``None`` so callers fall back to the placeholder.
"""
import io
import os
import re
import time
import uuid

from flask import current_app

try:  # Pillow ships with reportlab, but never let a missing import break the app.
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None

KINDS = ('student', 'teacher')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp'}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024      # 5 MB raw upload
MAX_DIMENSION = 600                      # stored image is at most 600 x 600
TMP_MAX_AGE_SECONDS = 24 * 3600
_TOKEN_RE = re.compile(r'^[0-9a-f]{32}$')
_FILE_RE = re.compile(r'^[0-9a-f]{32}\.jpg$')


class PhotoError(ValueError):
    """Raised for an unusable upload (wrong type, too big, not an image)."""


def _root():
    configured = current_app.config.get('PHOTO_UPLOAD_DIR')
    return configured or os.path.join(current_app.instance_path, 'uploads')


def _kind_dir(kind):
    if kind not in KINDS:
        raise ValueError('Unknown photo kind: %r' % (kind,))
    path = os.path.join(_root(), kind + 's')
    os.makedirs(path, exist_ok=True)
    return path


def _tmp_dir():
    path = os.path.join(_root(), 'tmp')
    os.makedirs(path, exist_ok=True)
    return path


def has_upload(file_storage):
    """True when the form really contains a chosen file."""
    return bool(file_storage and getattr(file_storage, 'filename', '')
                and file_storage.filename.strip())


def _process(file_storage):
    """Validate an upload and return JPEG bytes."""
    if Image is None:
        raise PhotoError('Photo uploads are unavailable (Pillow is not installed).')
    name = (file_storage.filename or '').strip()
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise PhotoError('Photo must be a JPG, PNG, WEBP, GIF or BMP image.')
    if hasattr(file_storage.stream, 'seek'):
        file_storage.stream.seek(0)
    raw = file_storage.stream.read(MAX_UPLOAD_BYTES + 1)
    if not raw:
        raise PhotoError('The selected photo is empty.')
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PhotoError('Photo is too large (maximum 5 MB).')
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        image = ImageOps.exif_transpose(image)
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGBA')
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert('RGB')
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
        out = io.BytesIO()
        image.save(out, format='JPEG', quality=88, optimize=True)
        return out.getvalue()
    except PhotoError:
        raise
    except Exception:
        raise PhotoError('That file is not a valid image.')


def _cleanup_tmp():
    try:
        cutoff = time.time() - TMP_MAX_AGE_SECONDS
        folder = _tmp_dir()
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                os.remove(full)
    except OSError:
        pass


def stash_upload(file_storage):
    """Keep an upload temporarily (used while a roll-number conflict is confirmed).

    Returns a token, or ``''`` when there is no file.  Raises PhotoError if invalid.
    """
    if not has_upload(file_storage):
        return ''
    data = _process(file_storage)
    _cleanup_tmp()
    token = uuid.uuid4().hex
    with open(os.path.join(_tmp_dir(), token + '.jpg'), 'wb') as handle:
        handle.write(data)
    return token


def save_photo(kind, file_storage=None, token=None):
    """Store a new photo and return its file name, or ``None`` if none supplied.

    A freshly chosen file wins over a stashed ``token``.  Raises PhotoError when
    the chosen file is unusable (the caller decides how to report it).
    """
    folder = _kind_dir(kind)
    if has_upload(file_storage):
        data = _process(file_storage)
    elif token and _TOKEN_RE.match(token):
        tmp_path = os.path.join(_tmp_dir(), token + '.jpg')
        if not os.path.isfile(tmp_path):
            return None
        with open(tmp_path, 'rb') as handle:
            data = handle.read()
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    else:
        return None
    filename = uuid.uuid4().hex + '.jpg'
    with open(os.path.join(folder, filename), 'wb') as handle:
        handle.write(data)
    return filename


def delete_photo(kind, filename):
    """Remove a stored photo file (ignores missing files / bad names)."""
    path = photo_path(kind, filename)
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


def photo_path(kind, filename):
    """Absolute path of an existing photo, else ``None`` (never raises)."""
    if not filename or not _FILE_RE.match(str(filename)):
        return None
    try:
        path = os.path.join(_kind_dir(kind), filename)
    except RuntimeError:  # no application context
        return None
    return path if os.path.isfile(path) else None


def square_image(path, size=400):
    """Centre-cropped square PIL image for ID cards / PDFs (or ``None``)."""
    if not path or Image is None:
        return None
    try:
        with Image.open(path) as image:
            image = image.convert('RGB')
            return ImageOps.fit(image, (size, size), centering=(0.5, 0.35))
    except Exception:
        return None


def square_image_buffer(path, size=300):
    """JPEG BytesIO of the square crop, for reportlab platypus ``Image``."""
    image = square_image(path, size)
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=88)
    buffer.seek(0)
    return buffer
