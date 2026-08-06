import os
from pathlib import Path
from datetime import datetime, date

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database & Data Paths
ORDERS_JSON_PATH = BASE_DIR / "orders.json"
POLICY_MD_PATH = BASE_DIR / "trendly_policy.md"

# Simulated Current Date (as per Section 5 of implementation plan)
# This date is critical to evaluate the 30-day return window accurately.
SIMULATED_CURRENT_DATE = date(2026, 8, 5)
SIMULATED_CURRENT_DATETIME = datetime(2026, 8, 5, 14, 0, 0)

# LLM Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash"
EMBEDDING_MODEL = "models/embedding-001"

# App settings
DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-trendly-agent")
