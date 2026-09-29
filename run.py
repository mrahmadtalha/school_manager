from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host=app.config.get('HOST', '127.0.0.1'), debug=app.config.get('DEBUG', False), port=app.config.get('PORT', 5000))