"""Flask application factory for Translate My Portfolio."""
from __future__ import annotations

import logging

from flask import Flask, render_template

from .extensions import limiter


def create_app(rate_limit_enabled: bool = True) -> Flask:
    """Build and configure the Flask app.

    ``rate_limit_enabled=False`` is used by the test suite so dozens of tests
    hitting /analyze in one process don't trip each other's rate limit; see
    tests/test_rate_limit.py for the test that runs the real limiter.
    """
    app = Flask(__name__)
    app.config["RATELIMIT_ENABLED"] = rate_limit_enabled
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # CSV uploads: 1 MB is plenty

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    limiter.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    _register_error_pages(app)
    return app


def _register_error_pages(app: Flask) -> None:
    """Friendly pages instead of Flask's bare default error screens."""

    def page(code: int, title: str, message: str):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(404)
    def not_found(_e):
        return page(404, "Page not found", "That page doesn't exist. Head back to the start to analyze a portfolio.")

    @app.errorhandler(413)
    def too_large(_e):
        return page(413, "File too large", "That CSV is over 1 MB. Try a smaller file (up to 200 rows).")

    @app.errorhandler(429)
    def rate_limited(_e):
        return page(429, "Slow down a little",
                    "You've run a lot of analyses in the last minute. Wait about a minute and try again.")

    @app.errorhandler(500)
    def server_error(_e):
        logging.getLogger(__name__).exception("Unhandled error")
        return page(500, "Something went wrong",
                    "An unexpected error happened on our side. Please try again; if it keeps happening, "
                    "try fewer holdings or different tickers.")
