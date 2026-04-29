import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug включаем только если явно передали FLASK_DEBUG=1.
    # В .env на проде стоит FLASK_ENV=production — сам factor-этого не делает,
    # поэтому debug читаем отдельно.
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    if not debug and os.getenv("FLASK_ENV", "").lower() == "development":
        debug = True
    app.run(host="0.0.0.0", port=5001, debug=debug)
