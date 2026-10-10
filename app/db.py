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

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
      user_id VARCHAR(32) PRIMARY KEY,
      email VARCHAR(255) NOT NULL UNIQUE,
      password_hash VARCHAR(255) NOT NULL,
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
      face_color VARCHAR(64) NULL,
      lip_color VARCHAR(64) NULL,
      tongue_body_color VARCHAR(64) NULL,
      tongue_coat_color VARCHAR(64) NULL,
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
      CONSTRAINT fk_health_user FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """,
]

EXTRA_COLUMNS = [
    ("health_records", "symptoms", "TEXT NULL"),
    ("health_records", "discomfort", "TEXT NULL"),
    ("health_records", "face_color", "VARCHAR(64) NULL"),
    ("health_records", "lip_color", "VARCHAR(64) NULL"),
    ("health_records", "tongue_body_color", "VARCHAR(64) NULL"),
    ("health_records", "tongue_coat_color", "VARCHAR(64) NULL"),
    ("health_records", "diet_advice", "VARCHAR(80) NULL"),
    ("health_records", "diet_url", "TEXT NULL"),
    ("health_records", "acupoint_url", "TEXT NULL"),
    ("health_records", "pulse_json", "TEXT NULL"),
] + [
    ("health_records", col, "VARCHAR(10) NOT NULL DEFAULT '未定'")
    for col in PATTERN_KEYS
]


def connect(with_db: bool = True, autocommit: bool = True):
    kwargs = dict(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=autocommit,
    )
    if with_db:
        kwargs["database"] = MYSQL_DATABASE
    return pymysql.connect(**kwargs)


def wait_for_mysql(timeout_seconds: int = 90):
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            conn = connect(with_db=True)
            conn.close()
            return
        except Exception as exc:  # pragma: no cover - boot-time retry
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"無法連線 MySQL：{last_error}")


def init_schema():
    wait_for_mysql()
    conn = connect(with_db=True)
    try:
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
    finally:
        conn.close()
