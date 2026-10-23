"""Entry point. Production servers import ``app`` from here (``run:app``);
``python run.py`` starts the local development server."""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
