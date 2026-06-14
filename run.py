"""ReviewBridge application entry point.

Run with: python run.py
Configure HOST, PORT, and FLASK_USE_RELOADER via environment variables (.env).
"""

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    # Reloader spawns a second process and clears in-memory FETCH_JOBS; keep off by default.
    use_reloader = os.getenv("FLASK_USE_RELOADER", "").strip().lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=True, use_reloader=use_reloader)
