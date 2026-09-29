"""Rebuild the cached fee summary rows from the fee ledger.

Usage
-----
    python scripts/rebuild_fee_summaries.py
    python scripts/rebuild_fee_summaries.py --month "September 2026"

The reconciliation page (``/fees/reconciliation``) flags any row where the
cached summary in ``fee_records`` disagrees with the sum of the
``fee_transactions`` ledger.  This script repairs those rows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.database import db  # noqa: E402
from app.services.fee_ledger import reconcile, repair_summaries  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description='Rebuild the cached fee summaries from the ledger.')
    parser.add_argument('--month', help='only rebuild this billing month, e.g. "September 2026"')
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        _, _, before = reconcile(args.month)
        if before:
            print(f'{len(before)} row(s) disagreed with the ledger before repair.')
        repaired = repair_summaries(args.month)
        _, totals, after = reconcile(args.month)

        print(f'Rows rebuilt    : {repaired}')
        print(f'Discrepancies   : {len(before)} -> {len(after)}')
        print(f'Totals charged  : {totals["charged"]}')
        print(f'Totals received : {totals["paid"]}')
        print(f'Outstanding     : {totals["balance"]}')
        if after:
            print('WARNING: discrepancies remain after repair.')
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
