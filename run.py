"""Start DIANA from the project root:  python run.py"""
from diana import config, create_app

app = create_app()

if __name__ == "__main__":
    print(f"DIANA online at http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, threaded=True)
