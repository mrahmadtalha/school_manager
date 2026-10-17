#!/usr/bin/env python
"""Vendor-side license tool.  NEVER ship this file or the ``vendor_keys`` folder.

Run from the project root::

    python tools/license_admin.py init
    python tools/license_admin.py issue --machine 7F3A-91BC-0D42-E8A5 \\
        --licensee "Al-Noor Public School, DG Khan" --days 365
    python tools/license_admin.py inspect --file al-noor.key
    python tools/license_admin.py machine-code

Features and WhatsApp caps (optional; omit them for a legacy "everything on" key)::

    python tools/license_admin.py issue --machine 7F3A-91BC-0D42-E8A5 \\
        --licensee "Al-Noor Public School" --days 365 --plan standard \\
        --features expenses,payroll,attendance,exams,whatsapp \\
        --wa-daily 100 --wa-monthly 2000 --rev 1

The vendor dashboard (``vendor_dashboard/``) does all of this from a web page
on your own laptop and is the recommended way to issue and renew keys.

Commands
--------
init          Create the signing key pair ONCE.  The private key goes to
              vendor_keys/license_private.key; the public key is written into
              app/services/license_public_key.py (rebuild the app afterwards).
              Refuses to overwrite an existing key: replacing it would invalidate
              every license already issued.
issue         Sign a license for one machine code.  Every issued license is also
              appended to vendor_keys/issued_licenses.csv for renewals/support.
inspect       Verify a key against the public key and print what it contains.
machine-code  Print the machine code of THIS computer (handy for testing).

BACK UP vendor_keys/license_private.key somewhere safe and private (for example
an encrypted USB stick).  If it is lost you cannot issue renewals: you would
have to generate a new pair, rebuild the app and re-issue every license.
"""

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = ROOT / 'vendor_keys'
PRIVATE_KEY_FILE = KEYS_DIR / 'license_private.key'
LEDGER_FILE = KEYS_DIR / 'issued_licenses.csv'
PUBLIC_KEY_MODULE = ROOT / 'app' / 'services' / 'license_public_key.py'


def _load_licensing():
    """Load app/services/licensing.py directly (avoids importing the Flask app)."""
    path = ROOT / 'app' / 'services' / 'licensing.py'
    spec = importlib.util.spec_from_file_location('sm_licensing', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lic = _load_licensing()


# -- key handling ---------------------------------------------------------

def load_private_key():
    if not PRIVATE_KEY_FILE.exists():
        sys.exit(f'No private key found at {PRIVATE_KEY_FILE}. Run "init" first.')
    raw = lic.b64u_decode(PRIVATE_KEY_FILE.read_text(encoding='utf-8').strip())
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_b64(private_key):
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return lic.b64u_encode(raw)


def build_payload(*, license_id, licensee, machine_code, issued, expires, grace_days,
                  rev=1, plan=None, features=None, wa_daily=None, wa_monthly=None):
    """The signed license payload (shared by this CLI and the vendor dashboard).

    ``features=None`` leaves the field out (legacy key: everything on);
    a list - even an empty one - switches exactly those modules on.  A missing
    WhatsApp cap means unlimited.
    """
    payload = {
        'v': lic.PAYLOAD_VERSION,
        'product': lic.PRODUCT,
        'license_id': license_id,
        'licensee': licensee.strip(),
        'machine_id': machine_code,
        'issued': issued.isoformat(),
        'expires': expires.isoformat(),
        'grace_days': max(0, min(lic.MAX_GRACE_DAYS, int(grace_days))),
        'rev': max(0, int(rev)),
    }
    if plan:
        payload['plan'] = str(plan)[:40]
    if features is not None:
        payload['features'] = sorted({str(item) for item in features})
    limits = {}
    if wa_daily is not None:
        limits[lic.LIMIT_WA_DAILY] = max(0, int(wa_daily))
    if wa_monthly is not None:
        limits[lic.LIMIT_WA_MONTHLY] = max(0, int(wa_monthly))
    if limits:
        payload['limits'] = limits
    return payload


def sign_license(private_key, payload):
    """Return the ``SM1.<payload>.<signature>`` key text for ``payload``."""
    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signature = private_key.sign(lic.SIGN_CONTEXT + payload_bytes)
    return f'{lic.KEY_PREFIX}.{lic.b64u_encode(payload_bytes)}.{lic.b64u_encode(signature)}'


# -- commands -------------------------------------------------------------

def cmd_init(args):
    if PRIVATE_KEY_FILE.exists() and not args.force:
        sys.exit(f'{PRIVATE_KEY_FILE} already exists. Replacing it would invalidate every license '
                 'you have issued. Use --force only if you really mean it.')
    KEYS_DIR.mkdir(exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    PRIVATE_KEY_FILE.write_text(lic.b64u_encode(raw) + '\n', encoding='utf-8')
    try:
        os.chmod(PRIVATE_KEY_FILE, 0o600)
    except OSError:
        pass

    pub = public_key_b64(private_key)
    text = PUBLIC_KEY_MODULE.read_text(encoding='utf-8')
    text = re.sub(r"PUBLIC_KEY_B64 = '.*'", f"PUBLIC_KEY_B64 = '{pub}'", text)
    PUBLIC_KEY_MODULE.write_text(text, encoding='utf-8')

    print(f'Private key written to {PRIVATE_KEY_FILE}  (KEEP SECRET, BACK IT UP)')
    print(f'Public key written into {PUBLIC_KEY_MODULE.relative_to(ROOT)}')
    print('Rebuild/restart the application so it picks up the new public key.')


def _catalog_keys():
    """Feature keys from app/services/features.py (loaded by path, no Flask needed)."""
    path = ROOT / 'app' / 'services' / 'features.py'
    spec = importlib.util.spec_from_file_location('sm_features', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ALL_FEATURES


def _next_license_id():
    count = 0
    if LEDGER_FILE.exists():
        with LEDGER_FILE.open(newline='', encoding='utf-8') as handle:
            count = max(0, sum(1 for _ in handle) - 1)
    return f'LIC-{date.today():%Y%m%d}-{count + 1:04d}'


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'license'


def cmd_issue(args):
    private_key = load_private_key()

    machine = lic.normalize_machine_code(args.machine)
    if len(machine) != 16:
        sys.exit('Machine code must look like 7F3A-91BC-0D42-E8A5 (16 letters/digits).')
    machine_code = '-'.join(machine[i:i + 4] for i in range(0, 16, 4))

    issued = date.fromisoformat(args.issued) if args.issued else date.today()
    if args.expires:
        expires = date.fromisoformat(args.expires)
    elif args.days:
        expires = issued + timedelta(days=args.days) - timedelta(days=1)
    else:
        sys.exit('Give either --days or --expires.')
    if expires < issued:
        sys.exit('Expiry cannot be before the issue date.')

    features = None
    if args.features is not None:
        known = set(_catalog_keys())
        wanted = [item.strip() for item in args.features.split(',') if item.strip()]
        features = sorted(known) if wanted == ['all'] else wanted
        unknown = sorted(set(features) - known)
        if unknown:
            sys.exit(f'Unknown feature(s): {", ".join(unknown)}. Known: {", ".join(sorted(known))}')

    payload = build_payload(
        license_id=args.license_id or _next_license_id(), licensee=args.licensee,
        machine_code=machine_code, issued=issued, expires=expires,
        grace_days=args.grace_days, rev=args.rev, plan=args.plan, features=features,
        wa_daily=args.wa_daily, wa_monthly=args.wa_monthly)
    key_text = sign_license(private_key, payload)

    KEYS_DIR.mkdir(exist_ok=True)
    new_file = not LEDGER_FILE.exists()
    with LEDGER_FILE.open('a', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(['created_at', 'license_id', 'licensee', 'machine_id',
                             'issued', 'expires', 'grace_days'])
        writer.writerow([datetime.now().isoformat(timespec='seconds'), payload['license_id'],
                         payload['licensee'], machine_code, payload['issued'],
                         payload['expires'], payload['grace_days']])

    out = Path(args.out) if args.out else KEYS_DIR / f'{_slug(payload["licensee"])}-{payload["license_id"]}.key'
    out.write_text(key_text + '\n', encoding='utf-8')

    print(f'License ID : {payload["license_id"]}')
    print(f'Licensee   : {payload["licensee"]}')
    print(f'Machine    : {machine_code}')
    print(f'Valid      : {payload["issued"]}  ->  {payload["expires"]}  (+{payload["grace_days"]} days grace)')
    print(f'Revision   : {payload["rev"]}   Plan: {payload.get("plan", "-")}')
    print(f'Features   : {", ".join(payload["features"]) if "features" in payload else "all (legacy key)"}')
    print(f'WhatsApp   : {payload.get("limits", "unlimited")}')
    print(f'Key file   : {out}')
    print('\nLicense key (send this to the school):\n')
    print(key_text)


def cmd_inspect(args):
    text = Path(args.file).read_text(encoding='utf-8-sig') if args.file else args.key
    if not text:
        sys.exit('Give a key with --key or a file with --file.')
    match = re.search(r"PUBLIC_KEY_B64 = '(.*)'", PUBLIC_KEY_MODULE.read_text(encoding='utf-8'))
    pub = match.group(1) if match else ''
    try:
        payload = lic.verify_license_text(text, pub)
    except lic.LicenseError as err:
        sys.exit(f'INVALID ({err.code}): {err.message}')
    print('Signature OK')
    for key in ('license_id', 'licensee', 'machine_id', 'issued', 'expires', 'grace_days',
                'rev', 'plan'):
        print(f'  {key:<11}: {payload.get(key)}')
    features = payload.get('_features')
    print(f'  {"features":<11}: {", ".join(features) if features is not None else "all (legacy key)"}')
    print(f'  {"limits":<11}: {payload.get("_limits") or "unlimited"}')


def cmd_machine_code(_args):
    print(lic.get_machine_code())


def main():
    parser = argparse.ArgumentParser(description='School Manager license tool (vendor only).')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('init', help='create the signing key pair (once)')
    p.add_argument('--force', action='store_true', help='overwrite an existing key (invalidates all licenses)')
    p.set_defaults(func=cmd_init)

    p = sub.add_parser('issue', help='issue a license for one machine')
    p.add_argument('--machine', required=True, help="the school computer's machine code")
    p.add_argument('--licensee', required=True, help='school name printed on the license')
    p.add_argument('--days', type=int, help='validity in days from the issue date (e.g. 365)')
    p.add_argument('--expires', help='explicit last valid day, YYYY-MM-DD')
    p.add_argument('--issued', help='issue date, YYYY-MM-DD (default: today)')
    p.add_argument('--grace-days', type=int, default=lic.DEFAULT_GRACE_DAYS,
                   help=f'days of full use after expiry before read-only (default {lic.DEFAULT_GRACE_DAYS})')
    p.add_argument('--license-id', help='override the automatic license ID')
    p.add_argument('--rev', type=int, default=1,
                   help='key revision; use a higher number to replace an earlier key of the same license ID')
    p.add_argument('--plan', help='plan label shown to the school (e.g. standard)')
    p.add_argument('--features', help='comma-separated feature keys, or "all"; omit for a legacy everything-on key')
    p.add_argument('--wa-daily', type=int, help='WhatsApp messages allowed per day (omit = unlimited)')
    p.add_argument('--wa-monthly', type=int, help='WhatsApp messages allowed per month (omit = unlimited)')
    p.add_argument('--out', help='where to write the .key file')
    p.set_defaults(func=cmd_issue)

    p = sub.add_parser('inspect', help='verify and display a license key')
    p.add_argument('--key', help='the key text')
    p.add_argument('--file', help='a .key file')
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser('machine-code', help='print this computer\'s machine code')
    p.set_defaults(func=cmd_machine_code)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
