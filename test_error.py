import traceback

try:
    from app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.get('/', follow_redirects=True)
    with open('debug_output.txt', 'w') as f:
        f.write("Status: " + str(resp.status_code) + "\n")
        if resp.status_code == 500:
            f.write(resp.data.decode('utf-8') + "\n")
except Exception:
    with open('debug_output.txt', 'w') as f:
        f.write(traceback.format_exc())
