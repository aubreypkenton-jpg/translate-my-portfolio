import logging

from flask import Flask

from .extensions import limiter


def create_app(rate_limit_enabled=True):
    """rate_limit_enabled=False is used by the test suite so 70+ tests
    hitting /analyze in one process don't trip each other's rate limit --
    see tests/test_rate_limit.py for the dedicated test that exercises the
    real limiter with enforcement turned on."""
    app = Flask(__name__)
    app.config["RATELIMIT_ENABLED"] = rate_limit_enabled

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    limiter.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    return app
