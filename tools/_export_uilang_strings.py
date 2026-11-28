"""Export UiLang.kt packs to Android strings.xml locale folders."""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "android/app/src/main/java/com/tube/healthing/UiLang.kt"
RES = ROOT / "android/app/src/main/res"

LOCALE_DIRS = {
    "zh": ["values", "values-zh-rTW"],
    "en": ["values-en"],
    "ja": ["values-ja"],
    "ko": ["values-ko"],
}

LANG_LABELS = {
    "lang_zh": "中文",
    "lang_en": "English",
    "lang_ja": "日本語",
    "lang_ko": "한국어",
}


def camel_to_snake(name: str) -> str:
    out = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    out = out.replace("-", "_").lower()
    out = re.sub(r"[^a-z0-9_]", "_", out)
    if out and out[0].isdigit():
        out = "n_" + out
    return out


def unescape_kt(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(n, n))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_packs(text: str) -> dict[str, dict[str, str]]:
    langs: dict[str, dict[str, str]] = {}
    # Find each `"xx" to mapOf(` then scan until matching close paren at map depth.
    for m in re.finditer(r'"(zh|en|ja|ko)"\s+to\s+mapOf\(', text):
        lang = m.group(1)
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == '"':
                i += 1
                while i < len(text):
                    if text[i] == "\\" and i + 1 < len(text):
                        i += 2
                        continue
                    if text[i] == '"':
                        i += 1
                        break
                    i += 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = text[start : i - 1]
        pairs = re.findall(r'"([^"]+)"\s+to\s+"((?:\\.|[^"\\])*)"', body)
        langs[lang] = {k: unescape_kt(v) for k, v in pairs}
    return langs


def xml_escape(s: str) -> str:
    s = s.replace("\\", "\\\\")
    s = s.replace("'", r"\'")
    s = s.replace('"', r"\"")
    return html.escape(s, quote=False)


def write_strings(path: Path, pairs: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    lines.append('    <string name="app_name">Health-ing</string>')
    seen = {"app_name"}
    for key in sorted(pairs.keys(), key=camel_to_snake):
        name = camel_to_snake(key)
        if name in seen:
            continue
        seen.add(name)
        lines.append(f'    <string name="{name}">{xml_escape(pairs[key])}</string>')
    for name, val in LANG_LABELS.items():
        if name not in seen:
            lines.append(f'    <string name="{name}">{xml_escape(val)}</string>')
            seen.add(name)
    lines.append("</resources>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    packs = parse_packs(SRC.read_text(encoding="utf-8"))
    counts = {k: len(v) for k, v in packs.items()}
    if set(packs) != {"zh", "en", "ja", "ko"}:
        raise SystemExit(f"unexpected langs: {sorted(packs)} counts={counts}")
    for lang, dirs in LOCALE_DIRS.items():
        for d in dirs:
            write_strings(RES / d / "strings.xml", packs[lang])
        print(lang, counts[lang], "->", ", ".join(dirs))


if __name__ == "__main__":
    main()
