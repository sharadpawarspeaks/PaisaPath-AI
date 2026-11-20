import sys
from pathlib import Path

# Add project root to sys.path so modules (config, models, routes, services) can be imported
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app import app
