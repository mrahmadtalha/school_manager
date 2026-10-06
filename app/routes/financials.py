"""Financial overview routes: monthly summary, period comparison, charts and
exports (admin only)."""

from flask import (Response, current_app, render_template, request, send_file)

from app.database import db
from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import financial_summary as summary_service
from app.services import payroll_service
from app.services.audit import log_action

#: Most periods we will display side by side before it stops being readable.
MAX_COMPARISON_PERIODS = 12


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


# --------------------------------------------------------------------------- #
# Comparison period selection
#
# The principal picks periods with plain-language presets or a month checklist;
# both end up as a list of period keys ('2026-09', 'year:2026',
# 'session:2026-2027') that the service understands.
# --------------------------------------------------------------------------- #

def _preset_periods(preset):
    """Period keys for a named preset, or None when it is not a known preset."""
    current = payroll_service.current_month_key()
    last_month = payroll_service.shift_month(current, -1)
    current_year = current[:4]
    session_start = summary_service.current_session_start_year()

    presets = {
        'this_vs_last': [last_month, current],
        'this_vs_last_year': [payroll_service.shift_month(current, -12), current],
        'last_3': payroll_service.recent_month_keys(current, 3),
        'last_6': payroll_service.recent_month_keys(current, 6),
        'last_12': payroll_service.recent_month_keys(current, 12),
        'this_year': ['year:%s' % current_year],
        'last_year': ['year:%d' % (int(current_year) - 1)],
        'this_session': ['session:%d' % session_start],
        'last_session': ['session:%d' % (session_start - 1)],
    }
    return presets.get(preset)


def _comparison_selection():
    """Resolve the requested comparison into (period_keys, preset_name, message)."""
    preset = (request.args.get('preset') or '').strip()
    raw = request.args.get('periods', '')

    if preset:
        keys = _preset_periods(preset)
        if not keys:
            return [], '', 'That comparison preset is not recognised.'
        # The checklist may add to a preset; keep the order and drop duplicates.
        extra = [part.strip() for part in raw.split(',') if part.strip()]
        keys = list(dict.fromkeys(list(keys) + extra))
        return keys[:MAX_COMPARISON_PERIODS], preset, ''

    keys = [part.strip() for part in raw.split(',') if part.strip()]
    keys = list(dict.fromkeys(keys))
    message = ''
    if len(keys) > MAX_COMPARISON_PERIODS:
        keys = keys[:MAX_COMPARISON_PERIODS]
        message = ('Showing the first %d periods — narrow the selection for a '
                   'clearer comparison.' % MAX_COMPARISON_PERIODS)
    return keys, '', message


def _comparison_context():
    """Everything the comparison panel and grid need (empty when not comparing)."""
    keys, preset, message = _comparison_selection()
    if not keys:
        return {'comparison': None, 'comparison_preset': preset,
                'comparison_message': message}

    snapshots = summary_service.period_snapshots(keys)
    if not snapshots:
        return {'comparison': None, 'comparison_preset': preset,
                'comparison_message': 'Those periods could not be read — '
                                      'please pick from the list below.'}

    rows = summary_service.comparison_rows(snapshots)
    totals = summary_service.comparison_totals(snapshots) if len(snapshots) > 1 else None
    return {
        'comparison': {
            'snapshots': snapshots,
            'period_keys': ','.join(s['key'] for s in snapshots),
            'period_key_list': [s['key'] for s in snapshots],
            'rows': rows['rows'],
            'show_difference': rows['show_difference'],
            'highlight': rows['highlight'],
            'totals': totals,
            'chart': {
                'labels': [s['short_label'] for s in snapshots],
                'revenue': [s['revenue'] for s in snapshots],
                'payroll': [s['payroll'] for s in snapshots],
                'expenses': [s['expenses'] for s in snapshots],
                'net': [s['net'] for s in snapshots],
            },
        },
        'comparison_preset': preset,
        'comparison_message': message,
    }


def _month_choices(count=24):
    """(key, label) pairs for the month checklist, newest first."""
    current = payroll_service.current_month_key()
    keys = list(reversed(payroll_service.recent_month_keys(current, count)))
    return [(key, summary_service.month_label(key)) for key in keys]


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
        month_choices=_month_choices(),
        max_comparison_periods=MAX_COMPARISON_PERIODS,
        **_comparison_context(),
        **ctx
    )


@main.route('/financials/summary/export.csv')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_export_csv():
    keys, preset, _message = _comparison_selection()
    if keys:
        snapshots = summary_service.period_snapshots(keys)
        if snapshots:
            rows = summary_service.comparison_rows(snapshots)['rows']
            totals = summary_service.comparison_totals(snapshots) if len(snapshots) > 1 else None
            text = summary_service.comparison_csv(snapshots, rows, totals)
            log_action('export', entity_type='FinancialSummary',
                       summary='Financial comparison exported to CSV (%s)'
                               % ', '.join(s['label'] for s in snapshots))
            db.session.commit()
            filename = 'financial_comparison_%s.csv' % keys[0].replace(':', '-')
            return Response(text, mimetype='text/csv',
                            headers={'Content-Disposition': 'attachment; filename=%s' % filename})

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
    keys, preset, _message = _comparison_selection()
    if keys:
        snapshots = summary_service.period_snapshots(keys)
        if snapshots:
            rows = summary_service.comparison_rows(snapshots)['rows']
            totals = summary_service.comparison_totals(snapshots) if len(snapshots) > 1 else None
            output = summary_service.comparison_pdf(snapshots, rows, totals,
                                                    current_app.root_path)
            log_action('export', entity_type='FinancialSummary',
                       summary='Financial comparison exported to PDF (%s)'
                               % ', '.join(s['label'] for s in snapshots))
            db.session.commit()
            filename = 'financial_comparison_%s.pdf' % keys[0].replace(':', '-')
            return send_file(output, mimetype='application/pdf', as_attachment=True,
                             download_name=filename)

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
