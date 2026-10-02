"""Financial overview routes: monthly summary, charts and exports (admin only)."""

from flask import (Response, current_app, render_template, request, send_file)

from app.database import db
from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import financial_summary as summary_service
from app.services import payroll_service
from app.services.audit import log_action


def _requested_month():
    value = (request.args.get('month') or '').strip()
    return value if payroll_service.parse_month(value) else payroll_service.current_month_key()


def _report_context():
    month = _requested_month()
    snapshot = summary_service.month_snapshot(month)
    return month, snapshot, dict(
        chart_payload={
            'trend': summary_service.trend_series(month, 6),
            'breakdown': summary_service.expense_breakdown(snapshot['start'],
                                                           snapshot['end']),
        },
        breakdown=summary_service.expense_breakdown(snapshot['start'], snapshot['end']),
        payroll_records=summary_service.payroll_rows(month),
    )


@main.route('/financials/summary')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_summary():
    month, snapshot, ctx = _report_context()
    return render_template(
        'financial_summary.html',
        month=month,
        snapshot=snapshot,
        prev_month=payroll_service.shift_month(month, -1),
        next_month=payroll_service.shift_month(month, 1),
        **ctx
    )


@main.route('/financials/summary/export.csv')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_export_csv():
    month, snapshot, ctx = _report_context()
    text = summary_service.report_csv(snapshot, ctx['breakdown'],
                                      ctx['payroll_records'])
    log_action('export', entity_type='FinancialSummary',
               summary='Financial summary exported to CSV (%s)' % month)
    db.session.commit()
    filename = 'financial_summary_%s.csv' % month.replace('-', '')
    return Response(text, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=%s' % filename})


@main.route('/financials/summary/export.pdf')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_export_pdf():
    month, snapshot, ctx = _report_context()
    output = summary_service.report_pdf(snapshot, ctx['breakdown'],
                                        ctx['payroll_records'],
                                        current_app.root_path)
    log_action('export', entity_type='FinancialSummary',
               summary='Financial summary exported to PDF (%s)' % month)
    db.session.commit()
    filename = 'financial_summary_%s.pdf' % month.replace('-', '')
    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=filename)
