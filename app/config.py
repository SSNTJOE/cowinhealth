import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "healthing")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "healthing")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "healthing")
SECRET_KEY = os.getenv("SECRET_KEY", "health-ing-dev-secret-change-me")
COOKIE_NAME = "healthing_session"
