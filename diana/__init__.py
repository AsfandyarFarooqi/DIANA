"""DIANA — Deployable Integrated Assembly of Neural Automation."""
from flask import Flask

from . import config

__version__ = "1.0.0"


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024

    from .routes import bp

    app.register_blueprint(bp)
    return app
