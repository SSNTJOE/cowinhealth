from __future__ import annotations

from functools import lru_cache

from .config import ROOT

RECIPE_PATH = ROOT / "Recipe.xls"
SPLIT_MARKS = ("、", ",", ";", "/", "，")


def split_tokens(text: str | None) -> list[str]:
    blob = (text or "").strip()
    if not blob:
        return []
    for mark in SPLIT_MARKS[1:]:
        blob = blob.replace(mark, SPLIT_MARKS[0])
    seen: set[str] = set()
    tokens: list[str] = []
    for part in blob.split(SPLIT_MARKS[0]):
        token = part.strip()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _open_sheet():
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("讀取 Recipe.xls 需要 xlrd==1.2.0") from exc
    if not RECIPE_PATH.exists():
        raise FileNotFoundError(str(RECIPE_PATH))
    return xlrd.open_workbook(str(RECIPE_PATH)).sheet_by_index(0)


@lru_cache(maxsize=4)
def _rows_cached(mtime_ns: int) -> tuple[dict[str, str], ...]:
    sheet = _open_sheet()
    headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
    last = max(sheet.ncols - 1, 0)
    rows: list[dict[str, str]] = []
    for row in range(1, sheet.nrows):
        rows.append(
            {
                "country": str(sheet.cell_value(row, 0)).strip() if sheet.ncols > 0 else "",
                "name_zh": str(sheet.cell_value(row, 1)).strip() if sheet.ncols > 1 else "",
                "name_en": str(sheet.cell_value(row, 2)).strip() if sheet.ncols > 2 else "",
                "recipe": str(sheet.cell_value(row, 5)).strip() if sheet.ncols > 5 else "",
                "benefit": str(sheet.cell_value(row, 6)).strip() if sheet.ncols > 6 else "",
                "ban": str(sheet.cell_value(row, 7)).strip() if sheet.ncols > 7 else "",
                "nutrient": str(sheet.cell_value(row, 8)).strip() if sheet.ncols > 8 else "",
                "allergens": str(sheet.cell_value(row, last)).strip(),
                "_headers": "\t".join(headers),
            }
        )
    return tuple(rows)


def recipe_rows() -> tuple[dict[str, str], ...]:
    path = RECIPE_PATH
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _rows_cached(mtime)


def allergen_labels() -> tuple[str, ...]:
    seen: set[str] = set()
    labels: list[str] = []
    try:
        rows = recipe_rows()
    except Exception:
        return ()
    for row in rows:
        for token in split_tokens(row.get("allergens")):
            if token not in seen:
                seen.add(token)
                labels.append(token)
    return tuple(sorted(labels))


def recipe_contains_allergen(allergen_cell: str, tokens: list[str]) -> bool:
    if not tokens:
        return False
    cell_tokens = set(split_tokens(allergen_cell))
    blob = allergen_cell or ""
    for token in tokens:
        if not token:
            continue
        if token in cell_tokens or token in blob:
            return True
    return False
