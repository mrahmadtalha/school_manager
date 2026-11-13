"""Small shared helpers of the financial summary: money rounding, month labels and the optional-module switch."""

from datetime import date

from app.database import db
from app.models import FeeTransaction
from app.services.payroll_service import parse_month


def short_label(month_year):
    parsed = parse_month(month_year)
    return date(parsed[0], parsed[1], 1).strftime('%b %Y') if parsed else ''


def _money(value):
    return round(float(value or 0), 2)


def _inventory_enabled():
    """Phase 3b gate: inventory/sales UI and metrics only exist when enabled."""
    from flask import current_app
    return bool(current_app.config.get('FEATURE_INVENTORY_SALES', False))


def _cash_date_column():
    """Explicit cash date where present, created date as legacy fallback."""
    return db.func.coalesce(FeeTransaction.payment_date,
                            db.func.date(FeeTransaction.created_at))


def _label_for_key(month_year):
    """'2026-09' -> 'September 2026' (the ledger's month label format)."""
    parsed = parse_month(month_year)
    return date(parsed[0], parsed[1], 1).strftime('%B %Y') if parsed else month_year
