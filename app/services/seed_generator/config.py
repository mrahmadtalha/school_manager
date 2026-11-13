"""``SeedConfig`` (what to generate) and ``_Progress`` (how the run reports back)."""

from dataclasses import dataclass

from .data import _STAGE_WEIGHTS


@dataclass
class SeedConfig:
    """Options for one demo-data generation run."""
    student_count: int = 60
    teacher_count: int = 8
    monthly_fee: float = 2500.0
    months: int = 12                      # history period, 1 = current month only
    include_attendance: bool = True
    include_fees: bool = True
    include_expenses: bool = True
    include_class_tests: bool = True
    include_term_exams: bool = True
    include_payroll: bool = True
    generate_photos: bool = False
    # Optional features.  All on by default so the demo school has *every*
    # screen filled in; each can be switched off (CLI: --no-inventory etc.).
    include_admission: bool = True        # admission-fee terms, receipts, books/uniform
    include_inventory: bool = True        # products, sets, purchases, sales, supplier dues
    include_canteen: bool = True          # canteen sales / purchases / supplier credit
    include_other_income: bool = True     # events, trips, activities, misc income
    include_documents: bool = True        # issued ID cards and certificates
    include_school_life: bool = True      # timetable, teaching load, remarks, QR, WhatsApp queue
    random_seed: int = 20261004


class _Progress:
    """Maps per-stage fractions onto one global 0-100 percentage."""

    def __init__(self, callback):
        self._cb = callback
        total = float(sum(w for _, w in _STAGE_WEIGHTS))
        offset = 0.0
        self._stages = {}
        for name, weight in _STAGE_WEIGHTS:
            self._stages[name] = (offset / total * 100.0, weight / total * 100.0)
            offset += weight
        self._last = -1

    def report(self, stage, fraction=0.0):
        if self._cb is None or stage not in self._stages:
            return
        base, span = self._stages[stage]
        percent = base + max(0.0, min(1.0, fraction)) * span
        rounded = int(percent)
        if rounded != self._last:
            self._last = rounded
            try:
                self._cb(stage, rounded)
            except Exception:
                pass
