import io
import csv
import pandas as pd
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# CLASS ATTENDANCE SHEET EXPORTS
# ==========================================

def generate_class_attendance_pdf(class_obj, students, selected_date, attendance_map=None, late_time_map=None):
    """
    Generates a printable PDF attendance sheet for a single class on a given date.
    If attendance was recorded, outputs actual statuses and totals; otherwise outputs a blank worksheet.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1a202c'), spaceAfter=5, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4a5568'), spaceAfter=15, alignment=1)
    
    is_recorded = bool(attendance_map)
    title_text = "School Management System — Attendance Report" if is_recorded else "School Management System — Attendance Sheet"
    story.append(Paragraph(title_text, title_style))
    
    if is_recorded:
        total = len(students)
        p_count = sum(1 for s in students if attendance_map.get(s.id) == 'Present')
        a_count = sum(1 for s in students if attendance_map.get(s.id) == 'Absent')
        l_count = sum(1 for s in students if attendance_map.get(s.id) == 'Late')
        sub_text = (f"<b>Class:</b> {class_obj.name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {selected_date} &nbsp;&nbsp;|&nbsp;&nbsp; "
                    f"<b>Total:</b> {total} &nbsp;&nbsp; <b>Present:</b> {p_count} &nbsp;&nbsp; <b>Absent:</b> {a_count} &nbsp;&nbsp; <b>Late:</b> {l_count}")
    else:
        sub_text = f"<b>Class:</b> {class_obj.name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Date:</b> {selected_date}"
        
    story.append(Paragraph(sub_text, subtitle_style))
    story.append(Spacer(1, 5))
    
    status_header = 'Status' if is_recorded else 'Status (P / A / L / LV)'
    table_data = [['Roll No', 'Student Name', 'Father Name', status_header, 'Remarks']]
    
    for s in students:
        if is_recorded:
            st = attendance_map.get(s.id, '—')
            if st == 'Late' and late_time_map and late_time_map.get(s.id):
                st = f"Late ({late_time_map[s.id]})"
        else:
            st = '___________________'
        table_data.append([str(s.roll_number), str(s.student_name), str(s.father_name), st, ''])
        
    t = Table(table_data, colWidths=[65, 130, 130, 110, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    output.seek(0)
    return output

def generate_class_attendance_excel(class_obj, students, attendance_map=None, late_time_map=None):
    """
    Generates an Excel workbook attendance sheet for a class.
    Shows real recorded statuses if available, otherwise blank template.
    """
    is_recorded = bool(attendance_map)
    data = []
    for s in students:
        if is_recorded:
            status = attendance_map.get(s.id, '—')
            if status == 'Late' and late_time_map and late_time_map.get(s.id):
                status = f"Late ({late_time_map[s.id]})"
        else:
            status = '—'
        data.append({
            'Roll Number': s.roll_number,
            'Student Name': s.student_name,
            'Father Name': s.father_name,
            'Status': status,
            'Remarks': ''
        })
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Class {class_obj.name}')
    output.seek(0)
    return output

def generate_class_attendance_csv(students, attendance_map=None, late_time_map=None):
    """
    Generates a CSV string representation of class attendance.
    Shows real recorded statuses if available, otherwise blank template.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll Number', 'Student Name', 'Father Name', 'Status', 'Remarks'])
    is_recorded = bool(attendance_map)
    for s in students:
        if is_recorded:
            status = attendance_map.get(s.id, '—')
            if status == 'Late' and late_time_map and late_time_map.get(s.id):
                status = f"Late ({late_time_map[s.id]})"
        else:
            status = ''
        writer.writerow([s.roll_number, s.student_name, s.father_name, status, ''])
    return output.getvalue()

# ==========================================
# TEACHER ATTENDANCE SHEET EXPORTS
# ==========================================

def generate_teacher_attendance_pdf(teachers, selected_date, attendance_map=None):
    """
    Generates a printable PDF attendance sheet for teachers on a given date.
    Shows real recorded statuses if available, otherwise blank sign-in sheet.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1a202c'), spaceAfter=5, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4a5568'), spaceAfter=15, alignment=1)
    
    is_recorded = bool(attendance_map)
    title_text = "School Management System — Teacher Attendance Report" if is_recorded else "School Management System — Teacher Attendance Sheet"
    story.append(Paragraph(title_text, title_style))
    
    if is_recorded:
        total = len(teachers)
        p_count = sum(1 for t in teachers if attendance_map.get(t.id) == 'Present')
        a_count = sum(1 for t in teachers if attendance_map.get(t.id) == 'Absent')
        sub_text = f"<b>Date:</b> {selected_date} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Total:</b> {total} &nbsp;&nbsp; <b>Present:</b> {p_count} &nbsp;&nbsp; <b>Absent:</b> {a_count}"
    else:
        sub_text = f"<b>Date:</b> {selected_date}"
        
    story.append(Paragraph(sub_text, subtitle_style))
    story.append(Spacer(1, 5))
    
    status_header = 'Status' if is_recorded else 'Status (P / A / L / LV)'
    table_data = [['Teacher ID', 'Teacher Name', 'Qualification', status_header, 'Signature / Remarks']]
    for t in teachers:
        status_val = attendance_map.get(t.id, '—') if is_recorded else '___________________'
        table_data.append([str(t.teacher_id_str), str(t.teacher_name), str(t.qualification), status_val, ''])
        
    t_table = Table(table_data, colWidths=[70, 130, 110, 110, 90])
    t_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_table)
    doc.build(story)
    output.seek(0)
    return output

def generate_teacher_attendance_excel(teachers, attendance_map=None):
    """
    Generates an Excel workbook attendance sheet for teachers.
    """
    is_recorded = bool(attendance_map)
    data = [{
        'Teacher ID': t.teacher_id_str,
        'Teacher Name': t.teacher_name,
        'Qualification': t.qualification,
        'Status': (attendance_map.get(t.id, '—') if is_recorded else '—'),
        'Remarks': ''
    } for t in teachers]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teacher Attendance')
    output.seek(0)
    return output

def generate_teacher_attendance_csv(teachers, attendance_map=None):
    """
    Generates a CSV string representation of teacher attendance.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Teacher ID', 'Teacher Name', 'Qualification', 'Status', 'Remarks'])
    is_recorded = bool(attendance_map)
    for t in teachers:
        status_val = attendance_map.get(t.id, '—') if is_recorded else ''
        writer.writerow([t.teacher_id_str, t.teacher_name, t.qualification, status_val, ''])
    return output.getvalue()

# ==========================================
# ATTENDANCE SUMMARY EXPORTS (MATRIX DATA)
# ==========================================

def generate_summary_excel(class_obj, students, dates_list, attendance_lookup):
    """
    Generates an Excel matrix summary for a class over a date range.
    """
    data = []
    for idx, s in enumerate(students, 1):
        row = {'Sr': idx, 'Roll No': s.roll_number, 'Student Name': s.student_name, 'Father Name': s.father_name}
        p = a = l = 0
        for d in dates_list:
            status = attendance_lookup.get((s.id, d), '—')
            row[d.strftime('%d/%m/%Y')] = status
            if status == 'Present': p += 1
            elif status == 'Absent': a += 1
            elif status == 'Late': l += 1
        row['Present'] = p
        row['Absent'] = a
        row['Late'] = l
        row['Attendance %'] = f'{round((p/len(dates_list))*100,1)}%' if dates_list else '0%'
        data.append(row)
        
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f'Summary {class_obj.name}')
    output.seek(0)
    return output

def generate_summary_csv(students, dates_list, attendance_lookup):
    """
    Generates a CSV string matrix summary for a class over a date range.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = ['Sr', 'Roll No', 'Student Name', 'Father Name'] + \
              [d.strftime('%d/%m/%Y') for d in dates_list] + \
              ['Present', 'Absent', 'Late', 'Attendance %']
    writer.writerow(headers)

    for idx, s in enumerate(students, 1):
        row = [idx, s.roll_number, s.student_name, s.father_name]
        p = a = l = 0
        for d in dates_list:
            status = attendance_lookup.get((s.id, d), '—')
            row.append(status)
            if status == 'Present': p += 1
            elif status == 'Absent': a += 1
            elif status == 'Late': l += 1
        row += [p, a, l, f'{round((p/len(dates_list))*100,1)}%' if dates_list else '0%']
        writer.writerow(row)
        
    return output.getvalue()

def generate_summary_pdf(class_obj, students, dates_list, attendance_lookup, start_date, end_date):
    """
    Generates a landscape PDF matrix summary report for a class.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(842, 595), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#1a202c'), spaceAfter=4, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#4a5568'), spaceAfter=12, alignment=1)

    story.append(Paragraph("Attendance Summary Report", title_style))
    story.append(Paragraph(f"<b>Class:</b> {class_obj.name} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Period:</b> {start_date} to {end_date}", subtitle_style))
    story.append(Spacer(1, 5))

    if not dates_list:
        story.append(Paragraph("No attendance records found for this period.", styles['Normal']))
        doc.build(story)
        output.seek(0)
        return output

    header_row = ['Sr', 'Roll No', 'Student Name'] + [d.strftime('%d/%m') for d in dates_list] + ['P', 'A', 'L', '%']
    table_data = [header_row]

    for idx, s in enumerate(students, 1):
        row = [str(idx), str(s.roll_number), str(s.student_name)]
        p = a = l = 0
        for d in dates_list:
            status = attendance_lookup.get((s.id, d), '—')
            if status == 'Present': short = 'P'; p += 1
            elif status == 'Absent': short = 'A'; a += 1
            elif status == 'Late': short = 'L'; l += 1
            elif status == 'Leave': short = 'LV'
            else: short = '—'
            row.append(short)
        pct = f'{round((p/len(dates_list))*100,1)}%' if dates_list else '0%'
        row += [str(p), str(a), str(l), pct]
        table_data.append(row)
        
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3748')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f7fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(t)
    doc.build(story)
    output.seek(0)
    return output
