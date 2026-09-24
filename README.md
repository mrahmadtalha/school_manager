# School Manager

A Flask-based school management application.

## Requirements

- Python 3.10+
- pip

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/macOS
   venv\Scripts\activate      # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   python run.py
   ```

## Environment variables

You can customize the app configuration with environment variables:

```bash
set APP_ENV=development
set SECRET_KEY=your-secret-key
set DATABASE_URL=sqlite:///school.db
set PORT=5000
```

For Linux/macOS, use `export` instead of `set`.

## Default login

- Username: `admin`
- Password: `admin123`

## Notes

The app creates the SQLite database automatically on first run.
