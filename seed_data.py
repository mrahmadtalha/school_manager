"""Populate the School Manager database with realistic *synthetic* demo data.

This script is a thin command-line wrapper around the advanced generator in
``app/services/seed_generator.py`` — the same engine the first-run setup
wizard uses.  It can produce months or years of history: students and
teachers with realistic ages and a join/leave lifecycle, daily attendance,
fees, expenses, tests, term exams with marks/results, and payroll.

Examples
--------
    python seed_data.py                                    # 60 students, 8 teachers, 1 year
    python seed_data.py --reset                            # wipe the database first
    python seed_data.py --students 500 --teachers 50 --months 120
    python seed_data.py --months 3 --no-payroll --photos

All names, phone numbers and amounts are fabricated.  No real student data is
used at any point.
"""

import argparse
import sys

from app import create_app
from app.services.seed_generator import SeedConfig, run_seed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reset', action='store_true',
                        help='drop every table and rebuild from scratch')
    parser.add_argument('--students', type=int, default=60, help='number of students (default 60)')
    parser.add_argument('--teachers', type=int, default=8, help='number of teachers (default 8)')
    parser.add_argument('--fee', type=float, default=2500.0, help='base monthly fee (default 2500)')
    parser.add_argument('--months', type=int, default=12,
                        help='history period in months: 1, 3, 6, 12, 24, 60, 120 (default 12)')
    parser.add_argument('--seed', type=int, default=20261004, help='random seed for reproducibility')
    parser.add_argument('--no-attendance', action='store_true', help='skip attendance generation')
    parser.add_argument('--no-fees', action='store_true', help='skip fee ledger generation')
    parser.add_argument('--no-expenses', action='store_true', help='skip expense generation')
    parser.add_argument('--no-tests', action='store_true', help='skip class tests and marks')
    parser.add_argument('--no-term-exams', action='store_true', help='skip term exams and results')
    parser.add_argument('--no-payroll', action='store_true', help='skip staff payroll')
    parser.add_argument('--photos', action='store_true',
                        help='generate optional dummy profile pictures (avatars)')

    args = parser.parse_args(argv)
    config = SeedConfig(
        student_count=max(0, args.students),
        teacher_count=max(0, args.teachers),
        monthly_fee=max(0.0, args.fee),
        months=min(240, max(1, args.months)),
        include_attendance=not args.no_attendance,
        include_fees=not args.no_fees,
        include_expenses=not args.no_expenses,
        include_class_tests=not args.no_tests,
        include_term_exams=not args.no_term_exams,
        include_payroll=not args.no_payroll,
        generate_photos=args.photos,
        random_seed=args.seed,
    )

    def on_progress(stage, percent):
        print(f'\r  [{percent:3d}%] {stage.replace("_", " "):<15}', end='', flush=True)

    app = create_app()
    with app.app_context():
        if args.reset:
            db_reset()
        summary = run_seed(config, on_progress)
        print()
        print('Seed complete.')
        for key in ('period_start', 'period_end', 'students', 'teachers',
                    'attendance_rows', 'fee_transactions', 'fee_records',
                    'expenses', 'class_tests', 'class_test_marks',
                    'term_exams', 'term_exam_tests', 'term_exam_marks',
                    'payroll_rows', 'photos'):
            if key in summary:
                print(f'  {key:<17}: {summary[key]}')
        print(f'  demo password    : {summary.get("demo_password")}')
    return 0


def db_reset():
    from app.database import db
    db.drop_all()
    db.create_all()
    print('Database reset: all tables dropped and recreated.')


if __name__ == '__main__':
    sys.exit(main())
