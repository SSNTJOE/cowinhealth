import logging
import threading
import time

import pymysql
from pymysql.cursors import DictCursor

from .config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)
from .syndrome import PATTERN_KEYS

logger = logging.getLogger(__name__)
_schema_ready = False
_schema_lock = threading.Lock()
_retry_started = False

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      user_id VARCHAR(32) PRIMARY KEY,
      email VARCHAR(255) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
      nickname VARCHAR(64) NULL,
      birth_year INT NULL,
      height DECIMAL(5,1) NULL,
      weight DECIMAL(5,1) NULL,
      age INT NULL,
      gender VARCHAR(20) NULL,
      medical_history TEXT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS health_records (
      record_id INT AUTO_INCREMENT PRIMARY KEY,
      user_id VARCHAR(32) NOT NULL,
      record_date DATETIME NOT NULL,
      symptoms TEXT NULL,
      discomfort TEXT NULL,
      face_color VARCHAR(255) NULL,
      lip_color VARCHAR(255) NULL,
      tongue_body_color VARCHAR(255) NULL,
      tongue_coat_color VARCHAR(255) NULL,
      heart_score INT NOT NULL,
      liver_score INT NOT NULL,
      spleen_score INT NOT NULL,
      lung_score INT NOT NULL,
      kidney_score INT NOT NULL,
      gallbladder_score INT NOT NULL,
      large_intestine_score INT NOT NULL,
      small_intestine_score INT NOT NULL,
      bladder_score INT NOT NULL,
      uterus_score INT NOT NULL,
      heart_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      liver_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      spleen_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      lung_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      kidney_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      gallbladder_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      large_intestine_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      small_intestine_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      bladder_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      uterus_pattern VARCHAR(10) NOT NULL DEFAULT '未定',
      diet_advice VARCHAR(80) NULL,
      diet_url TEXT NULL,
      acupoint_url TEXT NULL,
      pulse_json TEXT NULL,
      face_grid_json TEXT NULL,
      face_measurements_json TEXT NULL,
      complexion_label VARCHAR(128) NULL,
      complexion_hex VARCHAR(16) NULL,
      complexion_hsv_json TEXT NULL,
      tongue_grid_json TEXT NULL,
      tongue_measurements_json TEXT NULL,
      CONSTRAINT fk_health_user FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """,
]

EXTRA_COLUMNS = [
    ("users", "email", "VARCHAR(255) NULL"),
    ("users", "password_hash", "VARCHAR(255) NULL"),
    ("users", "nickname", "VARCHAR(64) NULL"),
    ("users", "birth_year", "INT NULL"),
    ("health_records", "symptoms", "TEXT NULL"),
    ("health_records", "discomfort", "TEXT NULL"),
    ("health_records", "face_color", "VARCHAR(255) NULL"),
    ("health_records", "lip_color", "VARCHAR(255) NULL"),
    ("health_records", "tongue_body_color", "VARCHAR(255) NULL"),
    ("health_records", "tongue_coat_color", "VARCHAR(255) NULL"),
    ("health_records", "diet_advice", "VARCHAR(80) NULL"),
    ("health_records", "diet_url", "TEXT NULL"),
    ("health_records", "acupoint_url", "TEXT NULL"),
    ("health_records", "pulse_json", "TEXT NULL"),
    ("health_records", "face_grid_json", "TEXT NULL"),
    ("health_records", "face_measurements_json", "TEXT NULL"),
    ("health_records", "complexion_label", "VARCHAR(128) NULL"),
    ("health_records", "complexion_hex", "VARCHAR(16) NULL"),
    ("health_records", "complexion_hsv_json", "TEXT NULL"),
    ("health_records", "tongue_grid_json", "TEXT NULL"),
    ("health_records", "tongue_measurements_json", "TEXT NULL"),
] + [
    ("health_records", col, "VARCHAR(10) NOT NULL DEFAULT '未定'")
    for col in PATTERN_KEYS
]

COLUMN_RESIZES = [
    ("health_records", "face_color", "VARCHAR(255) NULL"),
    ("health_records", "lip_color", "VARCHAR(255) NULL"),
    ("health_records", "tongue_body_color", "VARCHAR(255) NULL"),
    ("health_records", "tongue_coat_color", "VARCHAR(255) NULL"),
    ("health_records", "complexion_label", "VARCHAR(128) NULL"),
]


def connect(with_db: bool = True, autocommit: bool = True, *, ensure: bool = True):
    if ensure and with_db:
        ensure_schema()
    kwargs = dict(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=autocommit,
        connect_timeout=10,
    )
    if with_db:
        kwargs["database"] = MYSQL_DATABASE
    return pymysql.connect(**kwargs)


def wait_for_mysql(timeout_seconds: int = 90) -> bool:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            conn = connect(with_db=True, ensure=False)
            conn.close()
            return True
        except Exception as exc:  # pragma: no cover - boot-time retry
            last_error = exc
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(2, remaining))
    logger.error("無法連線 MySQL：%s", last_error)
    return False


def init_schema(timeout_seconds: int = 8) -> bool:
    global _schema_ready
    if _schema_ready:
        return True
    with _schema_lock:
        if _schema_ready:
            return True
        if not wait_for_mysql(timeout_seconds):
            return False
        conn = None
        try:
            conn = connect(with_db=True, ensure=False)
            with conn.cursor() as cur:
                for statement in SCHEMA_SQL:
                    cur.execute(statement)
                for table, column, ddl in EXTRA_COLUMNS:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
                        """,
                        (MYSQL_DATABASE, table, column),
                    )
                    if cur.fetchone()["c"] == 0:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                for table, column, ddl in COLUMN_RESIZES:
                    cur.execute(f"ALTER TABLE {table} MODIFY COLUMN {column} {ddl}")
            _schema_ready = True
            logger.info("MySQL schema ready")
            return True
        except Exception as exc:
            logger.error("初始化 MySQL schema 失敗：%s", exc)
            return False
        finally:
            if conn is not None:
                conn.close()


def ensure_schema() -> bool:
    return init_schema(timeout_seconds=2)


def start_schema_retry_loop() -> None:
    global _retry_started
    if _schema_ready or _retry_started:
        return
    _retry_started = True

    def _loop():
        while not init_schema(timeout_seconds=5):
            time.sleep(5)

    threading.Thread(target=_loop, name="mysql-schema-retry", daemon=True).start()


def ping_mysql() -> bool:
    try:
        init_schema(timeout_seconds=2)
        conn = connect(with_db=True, ensure=False)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                row = cur.fetchone()
            return bool(row and row["ok"] == 1)
        finally:
            conn.close()
    except Exception as exc:
        logger.error("MySQL ping failed: %s", exc)
        return False
