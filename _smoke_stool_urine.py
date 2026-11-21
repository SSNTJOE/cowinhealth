"""Synthetic steatorrhea score smoke: oily pale vs matte brown (teaching, no photos saved)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.stool_urine import analyze_stool_image


def _matte_brown(size: int = 160) -> Image.Image:
    img = Image.new("RGB", (size, size), (88, 58, 36))
    d = ImageDraw.Draw(img)
    d.ellipse([20, 25, 140, 135], fill=(118, 78, 44))
    d.ellipse([40, 42, 120, 115], fill=(105, 68, 40))
    px = img.load()
    for y in range(size):
        for x in range(size):
            if (x - 80) ** 2 + (y - 80) ** 2 > 62**2:
                px[x, y] = (62, 78, 88)
    return img


def _oily_pale(size: int = 160) -> Image.Image:
    img = Image.new("RGB", (size, size), (235, 210, 95))
    d = ImageDraw.Draw(img)
    d.ellipse([18, 22, 142, 128], fill=(240, 215, 100))
    d.ellipse([30, 35, 130, 115], fill=(245, 220, 110))
    for cx, cy, r in [
        (50, 48, 5),
        (72, 42, 6),
        (98, 50, 4),
        (60, 68, 4),
        (88, 70, 5),
        (110, 80, 4),
        (55, 90, 3),
        (95, 95, 4),
        (75, 58, 3),
    ]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 254, 250))
    px = img.load()
    for y in range(size):
        for x in range(size):
            if (x - 80) ** 2 + (y - 80) ** 2 > 58**2:
                base = 190 if y < 75 else 145
                ripple = ((x * 7 + y * 13) % 19) - 9
                v = max(0, min(255, base + ripple * 4))
                px[x, y] = (min(255, v + 8), min(255, v + 2), max(0, v - 30))
    for cx, cy in [(12, 28), (148, 22), (15, 95), (145, 100), (30, 15), (128, 18), (20, 50)]:
        d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 255, 253))
    return img


def main() -> None:
    matte = analyze_stool_image(_matte_brown(), color_temperature_k=5500)
    oily = analyze_stool_image(_oily_pale(), color_temperature_k=5500)
    ms = matte["stool"]["steatorrhea"]
    os_ = oily["stool"]["steatorrhea"]
    print("matte", matte["stool"]["class"]["id"], ms["score"], ms["triggered"])
    print("oily ", oily["stool"]["class"]["id"], os_["score"], os_["triggered"], oily["stool"]["class"].get("via"))
    print("formula", os_["formula"])
    ok = (
        not ms["triggered"]
        and matte["stool"]["class"]["id"] != "pale_oily"
        and oily["stool"]["class"]["id"] == "pale_oily"
        and os_["triggered"]
        and os_["score"] > ms["score"]
    )
    print("PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
