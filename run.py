import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    # Default: no reloader so in-memory fetch jobs survive refresh (Flask debug reloader uses 2 processes).
    use_reloader = os.getenv("FLASK_USE_RELOADER", "").strip().lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=True, use_reloader=use_reloader)
