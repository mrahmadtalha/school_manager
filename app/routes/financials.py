"""Financial overview routes: monthly summary, period comparison, charts and
exports (admin only)."""

from datetime import date

from flask import (Response, current_app, render_template, request, send_file)

from app.database import db
from app.models import ROLE_ACCOUNTANT, ROLE_ADMIN
from app.routes import main
from app.security import role_required
from app.services import financial_summary as summary_service
from app.services import inventory_service, payroll_service
from app.services import report_insights
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
        former_students_summary=summary_service.former_students_summary,
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


def _summary_charts(month, snapshot):
    """The four Phase 2b chart payloads (all rupees, shared engine data)."""
    months = payroll_service.recent_month_keys(month, 12)
    trend = summary_service.trend_series(month, 12)
    first_start = payroll_service.month_bounds(months[0])[0]
    last_end = payroll_service.month_bounds(months[-1])[1]
    outstanding = summary_service.month_fee_buckets(first_start, last_end)['outstanding']
    categories = summary_service.expense_breakdown(snapshot['start'], snapshot['end'])
    return {
        'labels': [t['label'] for t in trend],
        'cash_in': [t['revenue'] for t in trend],
        'cash_out': [t['expenses'] for t in trend],
        'collection': [summary_service.collection_split(m)['current'] for m in months],
        'outstanding': [round(outstanding.get(m, 0) / 100.0, 2) for m in months],
        'category_labels': [c['name'] for c in categories],
        'category_values': [c['total'] for c in categories],
    }


@main.route('/financials/summary')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_summary():
    month, snapshot, ctx = _report_context()
    range_start = (request.args.get('range_start') or '').strip() or None
    range_end = (request.args.get('range_end') or '').strip() or None
    comparisons, custom_comparison = summary_service.summary_comparisons(
        month, range_start, range_end)
    session_year = summary_service.current_session_start_year(
        date(int(month[:4]), int(month[5:]), 1))
    session_key = 'session:%d' % session_year
    range_period_keys = ''
    if custom_comparison:
        cur = custom_comparison['current']
        range_period_keys = ','.join(
            summary_service.months_in_range(cur['start'], cur['end']))
    return render_template(
        'financial_summary.html',
        month=month,
        snapshot=snapshot,
        fee_month=summary_service.fee_month_overview(month),
        salary_remaining=summary_service.salary_remaining_total(),
        comparisons=comparisons,
        custom_comparison=custom_comparison,
        range_start=range_start or '',
        range_end=range_end or '',
        session_key=session_key,
        range_period_keys=range_period_keys,
        alerts=summary_service.summary_alerts(month),
        insights=summary_service.summary_insights(month),
        revenue_impact=summary_service.former_revenue_impact(),
        charts=_summary_charts(month, snapshot),
        prev_month=payroll_service.shift_month(month, -1),
        next_month=payroll_service.shift_month(month, 1),
        month_choices=_month_choices(),
        inventory_enabled=inventory_service.inventory_enabled(),
        max_comparison_periods=MAX_COMPARISON_PERIODS,
        **_comparison_context(),
        **ctx
    )


@main.route('/financials/insights')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_insights():
    """Phase 4: rule-based insights, metrics and recommendations."""
    month = _requested_month()
    metrics = report_insights.period_metrics(month)      # computed once, shared
    return render_template(
        'financial_insights.html',
        month=month,
        metrics=metrics,
        insights=report_insights.insight_lines(month, metrics),
        recommendations=report_insights.recommendation_items(month, metrics),
        prev_month=payroll_service.shift_month(month, -1),
        next_month=payroll_service.shift_month(month, 1),
    )


@main.route('/financials/student-outstanding')
@role_required(ROLE_ADMIN, ROLE_ACCOUNTANT)
def financials_student_outstanding():
    """Student-wise dues list with plain filters (class, section, month,
    active / former / all)."""
    from app.models import ClassModel, SectionModel

    class_id = request.args.get('class_id', type=int)
    section_id = request.args.get('section_id', type=int)
    month = (request.args.get('month') or '').strip()
    status = (request.args.get('status') or 'active').strip()
    if status not in ('active', 'former', 'all'):
        status = 'active'
    if month and not payroll_service.parse_month(month):
        month = ''

    rows = summary_service.student_outstanding_rows(class_id, section_id, month,
                                                    status)
    return render_template(
        'student_outstanding.html',
        rows=rows,
        total_due=round(sum(r['outstanding'] for r in rows), 2),
        with_dues=sum(1 for r in rows if r['outstanding'] > 0),
        classes=ClassModel.query.order_by(ClassModel.name).all(),
        sections=SectionModel.query.order_by(SectionModel.name).all(),
        selected_class=class_id,
        selected_section=section_id,
        selected_month=month,
        selected_status=status,
        month_choices=_month_choices(),
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
