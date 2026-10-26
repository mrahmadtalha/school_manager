"""Make a SMALL zip of the project that is safe to share (no data, no secrets, no build junk).

Put this file in the project folder (next to run.py) and run:

    python make_zip.py            -> normal small zip  (code + templates + tests + docs)
    python make_zip.py --lite     -> smallest zip for AI sharing (also leaves out Android app,
                                     WhatsApp service, installer, screenshots, bundled
                                     JS/CSS libraries and fonts)
    python make_zip.py --changed 2   -> only files changed in the last 2 hours (e.g. to
                                        double-check what you edited)
    python make_zip.py --out D:\\share\\x.zip   -> choose the output file

The zip is saved NEXT TO the project folder as  school_project_small.zip  (or --lite name).
It also prints what was left out, so you can see nothing important is missing.
"""
import argparse
import fnmatch
import os
import time
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(ROOT)

MAX_FILE_MB = 5  # any single file bigger than this is left out (and listed)

# Never included (any level of the tree)
SKIP_DIRS = {
    # Python / tests
    "__pycache__", ".pytest_cache", ".pytest_tmp", "my_temp", "venv", ".venv", ".git",
    # data and secrets (never share these)
    "instance", "session", "vendor_keys", "vendor_data",
    # build output / downloads
    "node_modules", "build", "dist", ".gradle", ".idea", ".cxx", "captures",
}
SKIP_FILES = [
    "*.pyc", "*.db", "*.sqlite*", "*.key", "*.enc", "*.state", "*.zip", "*.log", "*.bak*",
    ".env", ".secret_key",
    # Android: build results, local paths and app-signing keys
    "*.apk", "*.aab", "local.properties", "*.jks", "*.keystore", "*.pem",
    # big listing files made by `tree /f`
    "structure.txt",
]

# Extra things left out only in --lite mode (paths relative to the project, use / )
LITE_SKIP_PREFIXES = [
    "android_guard_app/",
    "whatsapp-service/",
    "installer/",
    "screenshots/",
    "app/static/vendor/",
    "app/static/fonts/",
]
LITE_SKIP_FILES = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.woff*", "*.ttf"]


def main():
    ap = argparse.ArgumentParser(description="Make a small, safe-to-share zip of the project.")
    ap.add_argument("--lite", action="store_true", help="smallest zip (code only)")
    ap.add_argument("--changed", type=float, metavar="HOURS",
                    help="only files modified in the last N hours")
    ap.add_argument("--out", help="output zip path")
    args = ap.parse_args()

    default_name = "school_project_lite.zip" if args.lite else "school_project_small.zip"
    if args.changed:
        default_name = "school_project_changed.zip"
    out = os.path.abspath(args.out) if args.out else os.path.join(PARENT, default_name)
    since = time.time() - args.changed * 3600 if args.changed else None

    count = 0
    left_out = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                if any(fnmatch.fnmatch(name, p) for p in SKIP_FILES):
                    continue
                if args.lite:
                    if any(rel.startswith(p) for p in LITE_SKIP_PREFIXES):
                        continue
                    if any(fnmatch.fnmatch(name.lower(), p) for p in LITE_SKIP_FILES):
                        continue
                try:
                    if since and os.path.getmtime(full) < since:
                        continue
                    if os.path.getsize(full) > MAX_FILE_MB * 1024 * 1024:
                        left_out.append(rel)
                        continue
                    z.write(full, rel)
                    count += 1
                except Exception as error:
                    print("skipped:", full, error)

    size_mb = os.path.getsize(out) / 1024 / 1024
    print(f"Done: {count} files, {size_mb:.1f} MB")
    print("Saved to:", out)
    if size_mb > 25:
        print("Tip: zip is big - run again with  --lite  to make it smaller.")
    if left_out:
        print(f"Left out (bigger than {MAX_FILE_MB} MB):")
        for path in left_out:
            print("  ", path)


if __name__ == "__main__":
    main()