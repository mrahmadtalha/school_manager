# WhatsApp Service

This service runs the WhatsApp QR scan and message sending flow for the school app.

## Install

```bash
npm install
```

## Run

```bash
npm start
```

## Environment

Use `.env` or set variables:

```bash
APP_PORT=3001
APP_HOST=0.0.0.0
FLASK_BASE_URL=http://127.0.0.1:5000
POLL_INTERVAL_MS=5000
SEND_DELAY_MS=15000
SESSION_PATH=./session
```

## Usage

1. Start the service.
2. Scan the QR code from the terminal/web response.
3. Queue messages from the Flask app.
4. Approved or auto messages are sent one-by-one with delay.
