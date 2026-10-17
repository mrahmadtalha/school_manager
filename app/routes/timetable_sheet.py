from flask import jsonify, render_template, request, send_file

from app.models.settings import get_timetable_structure
from app.routes import main
from app.services import timetable_sheet as sheet


@main.route('/timetable')
def timetable_page():
    structure = get_timetable_structure()
    data = {
        'start_time': sheet.get_start_time(),
        'columns': sheet.build_columns(structure),
        'rows': sheet.load_sheet(),
        'teachers': sheet.teacher_options(),
        'classes': sheet.class_options(),
    }
    return render_template('timetable_sheet.html', data=data, structure=structure)


@main.route('/timetable/save', methods=['POST'])
def timetable_sheet_save():
    ok, error = sheet.save_sheet(request.get_json(silent=True))
    if not ok:
        return jsonify({'ok': False, 'error': error}), 400
    return jsonify({'ok': True})


@main.route('/timetable/pdf')
def timetable_sheet_pdf():
    orientation = 'portrait' if request.args.get('orientation') == 'portrait' else 'landscape'
    return send_file(sheet.build_pdf(orientation), mimetype='application/pdf',
                     as_attachment=True, download_name='timetable_%s.pdf' % orientation)
