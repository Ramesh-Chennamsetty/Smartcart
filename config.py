import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))


SECRET_KEY = os.environ.get("SMARTCART_SECRET_KEY", "abc123")


DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "root"  
DB_NAME = "codegnan"


MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'rameshchennamsetty12@gmail.com'
MAIL_PASSWORD = 'yeqh rjaz icqv palm'   

# Keep payment credentials outside source control. Set these before starting
# the application (Razorpay test-mode keys are recommended for development).
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
