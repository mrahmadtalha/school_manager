from app import create_app

app = create_app()

def _bind_host():
    """127.0.0.1 normally; 0.0.0.0 when guard phones are allowed (QR Attendance page).

    A HOST environment variable always wins.
    """
    import os
    if os.environ.get('HOST'):
        return app.config.get('HOST', '127.0.0.1')
    try:
        with app.app_context():
            from app.services.qr_attendance import lan_access_wanted
            if lan_access_wanted():
                print('Guard phone access is ON: listening on the school network.', flush=True)
                return '0.0.0.0'
    except Exception:
        pass
    return app.config.get('HOST', '127.0.0.1')


if __name__ == '__main__':
    host = _bind_host()
    port = app.config.get('PORT', 5000)
    if host == '0.0.0.0':
        try:   # lets guard phones find this computer again if its address changes
            from app.services.qr_pairing import start_discovery_responder
            start_discovery_responder(port)
        except Exception:
            pass
    app.run(host=host, debug=app.config.get('DEBUG', False), port=port)