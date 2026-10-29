import os
import sys
from pathlib import Path

# Add project root directory to sys.path so 'app' package resolves cleanly on Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from flask import Flask
from app import create_app

# Top-level Flask application instance for Vercel
env = os.getenv("FLASK_ENV", "production")
app: Flask = create_app(env)
