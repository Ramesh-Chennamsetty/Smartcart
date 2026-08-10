import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

SECRET_KEY = os.environ.get("SMARTCART_SECRET_KEY", "abc123")

# SQLite database path (used by application)
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "smartcart.db"))

# Legacy/MySQL configs (fallbacks)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
DB_NAME = os.environ.get("DB_NAME", "codegnan")

# Email Configuration
MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True").lower() == "true"
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "rameshchennamsetty12@gmail.com")
# Note: In production, set these variables in your environment or local .env file.
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "yeqh rjaz icqv palm")

# Payment Gateway Credentials
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_TLlVcS4DCvoErH").strip()
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "U0MlS25fYQOdT7pWFE2lN8mf").strip()
