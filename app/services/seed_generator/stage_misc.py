"""Stages: avatar photos and the admin/guardian accounts."""

import io
import os
import uuid

from flask import current_app

from app.database import db
from app.models import (ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER, AdminUser, GuardianStudentLink, StudentModel,
                        TeacherModel)

from .data import AVATAR_PALETTE, DEMO_USERS


def _stage_photos(rng, cfg, progress):
    """Optional locally drawn avatar JPEGs — nothing else in the app changes."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # Pillow missing: photos stay optional, skip quietly.
        progress.report('photos', 1.0)
        return 0

    def avatar_bytes(initials, color):
        size = 320
        img = Image.new('RGB', (size, size), color)
        draw = ImageDraw.Draw(img)
        light = tuple(min(255, channel + 60) for channel in color)
        draw.ellipse([36, 36, size - 36, size - 36], fill=light)
        font = None
        for font_name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
            try:
                font = ImageFont.truetype(font_name, 128)
                break
            except OSError:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(128)
            except TypeError:
                font = ImageFont.load_default()
        left, top, right, bottom = draw.textbbox((0, 0), initials, font=font)
        draw.text(((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
                  initials, fill='white', font=font)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()

    def photo_dir(kind):
        root = (current_app.config.get('PHOTO_UPLOAD_DIR')
                or os.path.join(current_app.instance_path, 'uploads'))
        path = os.path.join(root, kind + 's')
        os.makedirs(path, exist_ok=True)
        return path

    created = 0
    targets = ([('student', s) for s in StudentModel.query.all()] +
               [('teacher', t) for t in TeacherModel.query.all()])
    for index, (kind, person) in enumerate(targets):
        if rng.random() > 0.6:
            continue
        parts = (person.student_name if kind == 'student' else person.teacher_name).split()
        initials = ''.join(part[0] for part in parts[:2]).upper() or 'S'
        filename = uuid.uuid4().hex + '.jpg'
        with open(os.path.join(photo_dir(kind), filename), 'wb') as handle:
            handle.write(avatar_bytes(initials, AVATAR_PALETTE[index % len(AVATAR_PALETTE)]))
        person.photo_filename = filename
        created += 1
        if index % 50 == 0:
            db.session.commit()
        progress.report('photos', index / max(1, len(targets)))

    db.session.commit()
    progress.report('photos', 1.0)
    return created


def _stage_accounts(rng, cfg, progress):
    """Documented demo accounts for every role (idempotent; the wizard already has its admin)."""
    import os as _os
    password = _os.environ.get('DEFAULT_DEMO_PASSWORD') or 'School@2026'

    def ensure(username, role, full_name, **links):
        user = AdminUser.query.filter_by(username=username).first()
        if user is None:
            user = AdminUser(username=username, role=role, full_name=full_name, **links)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        return user

    ensure('admin', ROLE_ADMIN, 'School Administrator')

    first_teacher = (TeacherModel.query.filter_by(is_active=True)
                     .order_by(TeacherModel.id).first())
    teacher_user = AdminUser.query.filter_by(username='teacher1').first()
    if teacher_user is None:
        teacher_user = ensure('teacher1', ROLE_TEACHER, first_teacher.teacher_name if first_teacher
                              else 'Demo Teacher', teacher_id=first_teacher.id if first_teacher else None)
    elif teacher_user.teacher_id is None and first_teacher is not None:
        teacher_user.teacher_id = first_teacher.id

    for username, role, full_name in DEMO_USERS:
        ensure(username, role, full_name)

    active = (StudentModel.query.filter_by(is_active=True).order_by(StudentModel.id).all())
    if active:
        first_student = active[0]
        parent = AdminUser.query.filter_by(username='parent1').first()
        if parent is None:
            parent = ensure('parent1', ROLE_PARENT, f'Guardian of {first_student.student_name}',
                            student_id=first_student.id)
            db.session.add(GuardianStudentLink(user_id=parent.id, student_id=first_student.id))
        # A second parent with two children, so the multi-child portal can be tried.
        if len(active) >= 3 and AdminUser.query.filter_by(username='parent2').first() is None:
            kids = active[1:3]
            parent2 = ensure('parent2', ROLE_PARENT, f'Guardian of {kids[0].student_name} and '
                             f'{kids[1].student_name}', student_id=kids[0].id)
            for kid in kids:
                db.session.add(GuardianStudentLink(user_id=parent2.id, student_id=kid.id))

    db.session.commit()
    progress.report('accounts', 1.0)
    return password
