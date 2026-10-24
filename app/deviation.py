"""One row per reading. SQLite holds every row; deviation.xls is the colored view."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any

import xlwt

from .config import ROOT
from .health_flags import user_conditions

logger = logging.getLogger(__name__)

DB_PATH = ROOT / "deviation.db"
XLS_PATH = ROOT / "deviation.xls"
XLS_ROW_LIMIT = 65000
# Same edge as analysis.NORMAL_DELTA_E: inside this ΔE the color is still in spec.
NORMAL_DELTA_E = 3.0
_LOCK = threading.Lock()

FACE_IDS = tuple(range(1, 13))
TONGUE_ZONES = (
    ("top", "舌上"),
    ("center", "舌中"),
    ("bottom", "舌下"),
    ("left", "舌左"),
    ("right", "舌右"),
)
GENDER_LABELS = {"female": "女", "male": "男", "other": "其他"}
# People with no disease and no discomfort are expected in this health-score band.
QUIET_LOW = 3.0
QUIET_HIGH = 6.0
SEVERE_HIGH = 2.0

HEADER = (
    ["年齡", "性別", "特殊疾病與不舒服"]
    + [f"臉色{cell_id}" for cell_id in FACE_IDS]
    + [f"{label}質／苔" for _zone_id, label in TONGUE_ZONES]
    + ["檢測時間", "年齡區塊", "臉色均分", "舌色均分", "舌苔均分", "三者均分", "學習標記"]
)


def age_band(age: int | None) -> str:
    if age is None or age < 0:
        return "未填"
    decade = min(int(age) // 10, 8)
    if decade >= 8:
        return "80+"
    start = decade * 10
    return f"{start}-{start + 9}"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _face_by_id(result: dict[str, Any]) -> dict[int, dict[str, Any]]:
    cells = ((result.get("face_grid") or {}).get("cells")) or []
    found: dict[int, dict[str, Any]] = {}
    for cell in cells:
        try:
            found[int(cell.get("id"))] = cell
        except (TypeError, ValueError):
            continue
    return found


def _tongue_by_id(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    zones = ((result.get("tongue_grid") or {}).get("zones")) or []
    return {str(zone.get("id")): zone for zone in zones if zone.get("id")}


def _complaint(profile: dict[str, Any] | None, symptoms: str, discomfort: str) -> str:
    diseases = "、".join(user_conditions(profile))
    uneasy = "、".join(part.strip() for part in (discomfort, symptoms) if part and part.strip())
    parts: list[str] = []
    if diseases:
        parts.append("特殊疾病：" + diseases)
    if uneasy:
        parts.append("不舒服：" + uneasy)
    return "；".join(parts) if parts else "無"


def _mark(complaint: str, mean_score: float | None) -> str:
    if complaint != "無":
        return "有不適，不列入無病參考"
    if mean_score is None:
        return "缺測"
    if mean_score <= SEVERE_HIGH:
        return "重症"
    if QUIET_LOW <= mean_score <= QUIET_HIGH:
        return "符合無病參考"
    if mean_score > QUIET_HIGH:
        return "高於無病參考"
    return "低於無病參考"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deviations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id TEXT,
          recorded_at TEXT NOT NULL,
          age INTEGER,
          age_band TEXT NOT NULL,
          gender TEXT NOT NULL,
          complaint TEXT NOT NULL,
          face_de TEXT NOT NULL,
          face_score TEXT NOT NULL,
          tongue_body_de TEXT NOT NULL,
          tongue_body_score TEXT NOT NULL,
          tongue_coat_de TEXT NOT NULL,
          tongue_coat_score TEXT NOT NULL,
          mean_face REAL,
          mean_body REAL,
          mean_coat REAL,
          mean_all REAL,
          learning_mark TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dev_age_sex ON deviations(age_band, gender)")
    return conn


def _dump(values: list[float | None]) -> str:
    return ",".join("" if value is None else f"{value:.1f}" for value in values)


def _load(text: str, width: int) -> list[float | None]:
    loaded: list[float | None] = []
    for part in (text or "").split(",")[:width]:
        if part == "":
            loaded.append(None)
        else:
            loaded.append(float(part))
    return loaded + [None] * (width - len(loaded))


def build_deviation_row(
    profile: dict[str, Any] | None,
    result: dict[str, Any],
    symptoms: str = "",
    discomfort: str = "",
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    when = recorded_at or datetime.now()
    try:
        age = int(profile["age"]) if profile.get("age") is not None else None
    except (TypeError, ValueError):
        age = None
    if age is None and profile.get("birth_year"):
        try:
            age = when.year - int(profile["birth_year"])
        except (TypeError, ValueError):
            age = None
    gender = GENDER_LABELS.get(str(profile.get("gender") or "").strip().lower(), "未填")
    complaint = _complaint(profile, symptoms, discomfort)
    face = _face_by_id(result)
    tongue = _tongue_by_id(result)
    face_de: list[float | None] = []
    face_score: list[float | None] = []
    for cell_id in FACE_IDS:
        cell = face.get(cell_id) or {}
        face_de.append(_number(cell.get("delta_e")))
        face_score.append(_number(cell.get("health_score")))
    body_de: list[float | None] = []
    body_score: list[float | None] = []
    coat_de: list[float | None] = []
    coat_score: list[float | None] = []
    for zone_id, _label in TONGUE_ZONES:
        zone = tongue.get(zone_id) or {}
        body_de.append(_number(zone.get("delta_e")))
        body_score.append(_number(zone.get("health_score")))
        coat_de.append(_number(zone.get("coat_delta_e")))
        coat_score.append(_number(zone.get("coat_health_score")))
    mean_face = _mean([value for value in face_score if value is not None])
    mean_body = _mean([value for value in body_score if value is not None])
    mean_coat = _mean([value for value in coat_score if value is not None])
    mean_all = _mean([value for value in (mean_face, mean_body, mean_coat) if value is not None])
    return {
        "recorded_at": when.strftime("%Y-%m-%d %H:%M:%S"),
        "age": age,
        "age_band": age_band(age),
        "gender": gender,
        "complaint": complaint,
        "face_de": face_de,
        "face_score": face_score,
        "tongue_body_de": body_de,
        "tongue_body_score": body_score,
        "tongue_coat_de": coat_de,
        "tongue_coat_score": coat_score,
        "mean_face": mean_face,
        "mean_body": mean_body,
        "mean_coat": mean_coat,
        "mean_all": mean_all,
        "learning_mark": _mark(complaint, mean_all),
    }


def _insert(conn: sqlite3.Connection, user_id: str, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO deviations (
          user_id, recorded_at, age, age_band, gender, complaint,
          face_de, face_score, tongue_body_de, tongue_body_score,
          tongue_coat_de, tongue_coat_score,
          mean_face, mean_body, mean_coat, mean_all, learning_mark
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            row["recorded_at"],
            row["age"],
            row["age_band"],
            row["gender"],
            row["complaint"],
            _dump(row["face_de"]),
            _dump(row["face_score"]),
            _dump(row["tongue_body_de"]),
            _dump(row["tongue_body_score"]),
            _dump(row["tongue_coat_de"]),
            _dump(row["tongue_coat_score"]),
            row["mean_face"],
            row["mean_body"],
            row["mean_coat"],
            row["mean_all"],
            row["learning_mark"],
        ),
    )


def _cohorts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT age_band, gender,
               COUNT(*) AS n_all,
               SUM(CASE WHEN complaint = '無' THEN 1 ELSE 0 END) AS n_quiet,
               AVG(CASE WHEN complaint = '無' THEN mean_face END) AS face_mean,
               AVG(CASE WHEN complaint = '無' THEN mean_body END) AS body_mean,
               AVG(CASE WHEN complaint = '無' THEN mean_coat END) AS coat_mean,
               AVG(CASE WHEN complaint = '無' THEN mean_all END) AS all_mean
        FROM deviations
        GROUP BY age_band, gender
        ORDER BY age_band, gender
        """
    ).fetchall()
    cohorts: list[dict[str, Any]] = []
    for item in rows:
        mean_all = None if item["all_mean"] is None else round(float(item["all_mean"]), 1)
        n_quiet = int(item["n_quiet"] or 0)
        if n_quiet < 5:
            verdict = "樣本不足"
        elif mean_all is None:
            verdict = "缺測"
        elif mean_all <= SEVERE_HIGH:
            verdict = "無病者均分落在1–2，視為重症，這個年齡性別的判讀偏嚴"
        elif QUIET_LOW <= mean_all <= QUIET_HIGH:
            verdict = "無病者均分在3–6，符合參考"
        elif mean_all > QUIET_HIGH:
            verdict = "無病者均分高於3–6，判讀偏鬆"
        else:
            verdict = "無病者均分低於3–6、尚未到1–2"
        cohorts.append(
            {
                "age_band": item["age_band"],
                "gender": item["gender"],
                "n_all": int(item["n_all"]),
                "n_quiet": n_quiet,
                "face_mean": None if item["face_mean"] is None else round(float(item["face_mean"]), 1),
                "body_mean": None if item["body_mean"] is None else round(float(item["body_mean"]), 1),
                "coat_mean": None if item["coat_mean"] is None else round(float(item["coat_mean"]), 1),
                "all_mean": mean_all,
                "verdict": verdict,
            }
        )
    return cohorts


def _font(color: str) -> xlwt.XFStyle:
    style = xlwt.XFStyle()
    font = xlwt.Font()
    font.colour_index = xlwt.Style.colour_map[color]
    style.font = font
    return style


_GREEN = None
_RED = None
_PLAIN = None


def _styles() -> tuple[xlwt.XFStyle, xlwt.XFStyle, xlwt.XFStyle]:
    global _GREEN, _RED, _PLAIN
    if _GREEN is None:
        _GREEN = _font("green")
        _RED = _font("red")
        _PLAIN = xlwt.XFStyle()
    return _GREEN, _RED, _PLAIN


def _delta_style(value: float | None, green: xlwt.XFStyle, red: xlwt.XFStyle, plain: xlwt.XFStyle) -> xlwt.XFStyle:
    if value is None:
        return plain
    return green if value <= NORMAL_DELTA_E else red


def _write_pair(sheet: xlwt.Worksheet, row_index: int, col: int, body: float | None, coat: float | None) -> None:
    green, red, plain = _styles()
    present = [value for value in (body, coat) if value is not None]
    if not present:
        sheet.write(row_index, col, "", plain)
        return
    text = "／".join(
        part
        for part in (
            "" if body is None else f"質{body:.1f}",
            "" if coat is None else f"苔{coat:.1f}",
        )
        if part
    )
    style = green if all(value <= NORMAL_DELTA_E for value in present) else red
    sheet.write(row_index, col, text, style)


def export_workbook(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT * FROM deviations ORDER BY id DESC LIMIT ?",
        (XLS_ROW_LIMIT,),
    ).fetchall()
    rows = list(reversed(rows))
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("檢測差異")
    green, red, plain = _styles()
    for col, title in enumerate(HEADER):
        sheet.write(0, col, title, plain)
        sheet.col(col).width = 256 * (22 if col >= 2 else 14)
    for row_index, item in enumerate(rows, start=1):
        face_de = _load(item["face_de"], 12)
        body_de = _load(item["tongue_body_de"], 5)
        coat_de = _load(item["tongue_coat_de"], 5)
        values = [
            "" if item["age"] is None else int(item["age"]),
            item["gender"],
            item["complaint"],
        ]
        for col, value in enumerate(values):
            sheet.write(row_index, col, value, plain)
        for offset, value in enumerate(face_de):
            style = _delta_style(value, green, red, plain)
            if value is None:
                sheet.write(row_index, 3 + offset, "", style)
            else:
                sheet.write(row_index, 3 + offset, value, style)
        for offset, (body, coat) in enumerate(zip(body_de, coat_de)):
            _write_pair(sheet, row_index, 15 + offset, body, coat)
        tail = [
            item["recorded_at"],
            item["age_band"],
            item["mean_face"],
            item["mean_body"],
            item["mean_coat"],
            item["mean_all"],
            item["learning_mark"],
        ]
        for offset, value in enumerate(tail):
            sheet.write(row_index, 20 + offset, "" if value is None else value, plain)
    learning = book.add_sheet("年齡性別學習")
    note = (
        "差異值是與教學正常色的ΔE。ΔE在3以內為綠色，超過為紅色。"
        "沒有特殊疾病、也沒有不舒服的人，臉色、舌色、舌苔平均健康分應在3到6；平均1到2視為重症。"
        "同一年齡區塊、同一性別累積至少5次無不適紀錄後，用這個範圍核對判讀偏鬆或偏嚴。"
        "完整每次紀錄在 deviation.db；本表只顯示最近65000列。"
    )
    learning.write_merge(0, 0, 0, 8, note, plain)
    learning_header = ["年齡區塊", "性別", "全部次數", "無不適次數", "臉色均分", "舌色均分", "舌苔均分", "三者均分", "對照"]
    for col, title in enumerate(learning_header):
        learning.write(1, col, title, plain)
        learning.col(col).width = 256 * (18 if col < 8 else 42)
    for row_index, cohort in enumerate(_cohorts(conn), start=2):
        learning.write(row_index, 0, cohort["age_band"], plain)
        learning.write(row_index, 1, cohort["gender"], plain)
        learning.write(row_index, 2, cohort["n_all"], plain)
        learning.write(row_index, 3, cohort["n_quiet"], plain)
        learning.write(row_index, 4, "" if cohort["face_mean"] is None else cohort["face_mean"], plain)
        learning.write(row_index, 5, "" if cohort["body_mean"] is None else cohort["body_mean"], plain)
        learning.write(row_index, 6, "" if cohort["coat_mean"] is None else cohort["coat_mean"], plain)
        learning.write(row_index, 7, "" if cohort["all_mean"] is None else cohort["all_mean"], plain)
        learning.write(row_index, 8, cohort["verdict"], plain)
    temporary = XLS_PATH.with_name("deviation.xls.new")
    book.save(str(temporary))
    os.replace(temporary, XLS_PATH)


def record_deviation(
    user_id: str,
    profile: dict[str, Any] | None,
    result: dict[str, Any],
    symptoms: str = "",
    discomfort: str = "",
) -> None:
    row = build_deviation_row(profile, result, symptoms, discomfort)
    with _LOCK:
        conn = _connect()
        try:
            _insert(conn, user_id, row)
            conn.commit()
            try:
                export_workbook(conn)
            except OSError:
                logger.warning("deviation.xls 正在被開啟，這次先寫入 deviation.db")
        finally:
            conn.close()
