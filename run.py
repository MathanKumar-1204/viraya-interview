"""
Main application runner for Viraya Company's Interview AI Bot.
Supports development mode (with Windows-safe reload and error suppression)
and production mode (using Waitress or standard WSGI).
"""
import os
import sys
import warnings

# 1. Suppress third-party PyMongo/cryptography negative serial number warning on Windows
warnings.filterwarnings("ignore", message=".*Parsed a negative serial number.*")
try:
    from cryptography.utils import CryptographyDeprecationWarning
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except Exception:
    pass

# 2. On Windows, gracefully handle socket closure during thread shutdown/reload
if sys.platform == "win32":
    import socketserver
    _orig_serve_forever = socketserver.BaseServer.serve_forever

    def _safe_serve_forever(self, poll_interval=0.5):
        try:
            _orig_serve_forever(self, poll_interval=poll_interval)
        except OSError as e:
            # WinError 10038 (WSAENOTSOCK) occurs when the reloader closes the listening socket from another thread
            if getattr(e, "winerror", None) == 10038 or e.errno in (10038, 9):
                return
            raise

    socketserver.BaseServer.serve_forever = _safe_serve_forever

from app import create_app

env = os.getenv("FLASK_ENV", "production")
app = create_app(env)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    use_production_server = os.getenv("USE_WAITRESS", "0") == "1" or "--prod" in sys.argv or "--production" in sys.argv

    if use_production_server:
        from waitress import serve
        print(f"* Starting Viraya Interview AI Bot on http://localhost:{port} (Production - Waitress WSGI)")
        serve(app, host="0.0.0.0", port=port, threads=8)
    else:
        # Development runner with safe reloader settings
        use_reloader = os.getenv("USE_RELOADER", "1" if debug else "0") == "1"
        print(f"* Viraya Interview AI Bot starting on http://localhost:{port} (Debug: {debug}, Reloader: {use_reloader})")
        app.run(
            host="0.0.0.0",
            port=port,
            debug=debug,
            use_reloader=use_reloader,
            exclude_patterns=["*site-packages*", "*AppData*"]
        )
