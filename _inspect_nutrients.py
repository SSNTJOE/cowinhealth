# -*- coding: utf-8 -*-
from pathlib import Path

out = []
root = Path(r"C:\tube\Health-ing")

# daily_nutrient.xlsx
xlsx = root / "daily_nutrient.xlsx"
out.append("=" * 60)
out.append(f"FILE: {xlsx}")
out.append(f"exists: {xlsx.exists()} size={xlsx.stat().st_size if xlsx.exists() else 0}")
out.append("=" * 60)

try:
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, data_only=True)
    out.append(f"sheets: {wb.sheetnames}")
    for name in wb.sheetnames:
        ws = wb[name]
        out.append(
            f"\n--- Sheet: {name} dims={ws.dimensions} "
            f"max_row={ws.max_row} max_col={ws.max_column} ---"
        )
        for r in range(1, (ws.max_row or 0) + 1):
            row_vals = []
            for c in range(1, (ws.max_column or 0) + 1):
                cell = ws.cell(r, c)
                row_vals.append(repr(cell.value))
            out.append(f"R{r}: " + " | ".join(row_vals))
except Exception as e:
    out.append(f"openpyxl error: {e}")
    try:
        import pandas as pd

        xl = pd.ExcelFile(xlsx)
        out.append(f"pandas sheets: {xl.sheet_names}")
        for name in xl.sheet_names:
            df = pd.read_excel(xlsx, sheet_name=name, header=None)
            out.append(f"\n--- Sheet: {name} shape={df.shape} ---")
            out.append(df.to_string())
    except Exception as e2:
        out.append(f"pandas error: {e2}")

# Recipe.xls
xls = root / "Recipe.xls"
out.append("\n" + "=" * 60)
out.append(f"FILE: {xls}")
out.append(f"exists: {xls.exists()} size={xls.stat().st_size if xls.exists() else 0}")
out.append("=" * 60)

try:
    import pandas as pd

    for eng in ["xlrd", "openpyxl", None]:
        try:
            kwargs = {"sheet_name": None}
            if eng:
                kwargs["engine"] = eng
            sheets = pd.read_excel(xls, **kwargs)
            out.append(
                f"engine={eng} sheets: "
                f"{list(sheets.keys()) if isinstance(sheets, dict) else 'single'}"
            )
            if not isinstance(sheets, dict):
                sheets = {"(default)": sheets}
            for name, df in sheets.items():
                out.append(f"\n--- Sheet: {name} shape={df.shape} ---")
                out.append(
                    "COLUMNS: " + " | ".join(str(c) for c in df.columns.tolist())
                )
                nutrient_kw = [
                    "熱量",
                    "膳食纖維",
                    "纖維",
                    "蛋白",
                    "脂肪",
                    "碳水",
                    "糖",
                    "鈉",
                    "鈣",
                    "鐵",
                    "維生",
                    "nutrient",
                    "calori",
                    "fiber",
                    "protein",
                    "fat",
                    "carb",
                    "sodium",
                ]
                nutrient_cols = [
                    c
                    for c in df.columns
                    if any(k in str(c) for k in nutrient_kw)
                ]
                out.append(
                    "NUTRIENT-RELATED COLUMNS: "
                    + (
                        ", ".join(str(c) for c in nutrient_cols)
                        if nutrient_cols
                        else "(none matched keywords)"
                    )
                )
                sample_n = min(2, len(df))
                out.append(f"\nSample first {sample_n} rows (all columns):")
                for i in range(sample_n):
                    out.append(f"--- row index {i} ---")
                    for c in df.columns:
                        v = df.iloc[i][c]
                        out.append(f"  {c!r}: {v!r}")
                if nutrient_cols:
                    out.append("\nSample nutrient numeric columns:")
                    for i in range(sample_n):
                        out.append(f"--- nutrient row {i} ---")
                        for c in nutrient_cols:
                            v = df.iloc[i][c]
                            out.append(
                                f"  {c!r}: {v!r} (type={type(v).__name__})"
                            )
            break
        except Exception as e:
            out.append(f"engine={eng} failed: {e}")
except Exception as e:
    out.append(f"Recipe.xls overall error: {e}")

# Meal feature code check
out.append("\n" + "=" * 60)
out.append("MEAL FEATURE CODE CHECK")
out.append("=" * 60)
modules = ["user_meals", "meal_calendar", "nutrient_targets"]
for mod in modules:
    hits = list(root.rglob(f"*{mod}*"))
    hits = [h for h in hits if "node_modules" not in str(h) and ".git" not in str(h)]
    out.append(f"{mod}: files={hits if hits else 'NONE'}")

text = "\n".join(out)
print(text)
(root / "_nutrient_inspect_out.txt").write_text(text, encoding="utf-8")
print("\n--- WROTE _nutrient_inspect_out.txt ---")
