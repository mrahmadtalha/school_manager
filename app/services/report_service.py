from app.models import (
    ClassModel, StudentModel, TestModel, StudentMarkModel
)

def calculate_grade(percentage, total_max):
    """
    Returns standard letter grade based on percentage score.
    """
    if total_max <= 0:
        return 'N/A'
    if percentage >= 85:   return 'A+'
    elif percentage >= 70: return 'A'
    elif percentage >= 60: return 'B'
    elif percentage >= 50: return 'C'
    elif percentage >= 40: return 'D'
    return 'F'

def build_class_results_matrix(selected_class_id, selected_type=''):
    """
    Builds the complete results matrix for a class, including student scores,
    percentage, letter grades, class ranks, and class-level KPI stats.
    """
    all_tests = TestModel.query.filter_by(class_id=selected_class_id).order_by(TestModel.test_date).all()
    test_types = sorted(set(t.test_type for t in all_tests if t.test_type))
    class_tests = [t for t in all_tests if not selected_type or t.test_type == selected_type]

    students = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()
    test_ids = [t.id for t in class_tests]
    all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all() if test_ids else []
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}

    matrix_data = []
    for s in students:
        student_row = {'student': s, 'scores': {}, 'grades': {}}
        total_obtained = 0.0
        total_max = 0.0

        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            if m:
                student_row['scores'][t.id] = m.marks_obtained
                student_row['grades'][t.id] = m.grade
                total_obtained += m.marks_obtained
            else:
                student_row['scores'][t.id] = None
                student_row['grades'][t.id] = None
            total_max += t.total_marks

        overall_pct = (total_obtained / total_max * 100) if total_max > 0 else 0.0
        student_row['total_obtained'] = total_obtained
        student_row['total_max'] = total_max
        student_row['percentage'] = round(overall_pct, 1)
        student_row['overall_grade'] = calculate_grade(overall_pct, total_max)
        matrix_data.append(student_row)

    # Sort by percentage descending to assign class rank
    matrix_data.sort(key=lambda x: x['percentage'], reverse=True)
    for i, row in enumerate(matrix_data, 1):
        row['rank'] = i

    summary = {}
    if matrix_data:
        percentages = [r['percentage'] for r in matrix_data if r['total_max'] > 0]
        pass_count = sum(1 for p in percentages if p >= 40)
        summary = {
            'total_students': len(matrix_data),
            'total_tests': len(class_tests),
            'class_avg': round(sum(percentages) / len(percentages), 1) if percentages else 0,
            'pass_rate': round((pass_count / len(percentages)) * 100, 1) if percentages else 0,
            'top_scorer': matrix_data[0]['student'].student_name if matrix_data else '—',
            'top_pct': matrix_data[0]['percentage'] if matrix_data else 0,
        }

    return {
        'test_types': test_types,
        'class_tests': class_tests,
        'matrix_data': matrix_data,
        'summary': summary
    }

def get_class_results_export_rows(selected_class_id):
    """
    Computes tabular data rows for Excel and CSV class result exports.
    """
    class_obj = ClassModel.query.get_or_404(selected_class_id)
    students = StudentModel.query.filter_by(is_active=True, class_id=selected_class_id).all()
    class_tests = TestModel.query.filter_by(class_id=selected_class_id).all()
    
    test_ids = [t.id for t in class_tests]
    all_marks = StudentMarkModel.query.filter(StudentMarkModel.test_id.in_(test_ids)).all() if test_ids else []
    marks_map = {(m.student_id, m.test_id): m for m in all_marks}

    rows = []
    for s in students:
        row_dict = {'Roll No': s.roll_number, 'Student Name': s.student_name, 'Father Name': s.father_name}
        row_list = [s.roll_number, s.student_name, s.father_name]
        total_ob = 0.0
        total_mx = 0.0

        for t in class_tests:
            m = marks_map.get((s.id, t.id))
            score_str = f"{m.marks_obtained} ({m.grade})" if m else "-"
            col_name = f"{t.test_title} ({t.test_type})"
            row_dict[col_name] = score_str
            row_list.append(score_str)
            if m: total_ob += m.marks_obtained
            total_mx += t.total_marks

        pct = (total_ob / total_mx * 100) if total_mx > 0 else 0.0
        total_str = f"{total_ob} / {total_mx}"
        pct_str = f"{round(pct, 1)}%"

        row_dict['Total Obtained'] = total_str
        row_dict['Percentage'] = pct_str
        row_list.extend([total_str, pct_str])

        rows.append({'dict': row_dict, 'list': row_list})

    return class_obj, class_tests, rows
