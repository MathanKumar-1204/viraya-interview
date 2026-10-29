import importlib.util
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

APP_PKG_DIR = ROOT_DIR / "app"
INIT_PY = APP_PKG_DIR / "__init__.py"

if "app" not in sys.modules or not hasattr(sys.modules["app"], "create_app"):
    spec = importlib.util.spec_from_file_location(
        "app",
        str(INIT_PY),
        submodule_search_locations=[str(APP_PKG_DIR)]
    )
    app_pkg = importlib.util.module_from_spec(spec)
    sys.modules["app"] = app_pkg
    spec.loader.exec_module(app_pkg)

create_app = sys.modules["app"].create_app

# Top-level Flask application instance for WSGI & Vercel
env = os.getenv("FLASK_ENV", "production")
app = create_app(env)

if __name__ == "__main__":
    app.run()
