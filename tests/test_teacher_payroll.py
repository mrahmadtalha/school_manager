from app.services.teacher_payroll import calculate_late_deduction


def test_calculate_late_deduction_for_hourly_teacher():
    deduction = calculate_late_deduction('09:15', '08:30', 500.0)
    assert deduction == 375.0


def test_calculate_late_deduction_for_on_time_teacher():
    deduction = calculate_late_deduction('08:20', '08:30', 500.0)
    assert deduction == 0.0
