"""Start the vendor dashboard:  python vendor_dashboard/run_dashboard.py

Opens http://127.0.0.1:5055 in your browser.  Bound to this laptop only.
"""

import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vendor_dashboard.app import create_app  # noqa: E402

HOST, PORT = '127.0.0.1', 5055


def main():
    app = create_app()
    url = f'http://{HOST}:{PORT}/'
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f'School Manager license dashboard: {url}   (Ctrl+C to stop)')
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=4)
    except ImportError:
        app.run(host=HOST, port=PORT, debug=False)


if __name__ == '__main__':
    main()
