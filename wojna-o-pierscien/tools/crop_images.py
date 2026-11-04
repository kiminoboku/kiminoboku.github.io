"""Crops images from the PDF rulebook into the img/ folder.

Requires poppler (pdftoppm) and macOS (sips, to convert large images to JPEG).
Coordinates are in PDF points (A4 page = 595 x 842 pt): (page, x0, y0, x1, y1).
Image names stay Polish because the files in src/ refer to them by name.
Usage: python3 tools/crop_images.py /path/to/WoP_instrukcja.pdf
"""
import subprocess
import sys
from pathlib import Path

DPI = 170
JPEG_ABOVE_BYTES = 250_000
OUT = Path(__file__).resolve().parent.parent / "img"

# x centre of each die-face column on page 19 (character, army, muster, event, muster/army, special)
DICE_X = {"postac": 91, "armia": 173, "mobilizacja": 256, "wydarzenie": 338,
          "mobilizacja-armia": 420, "specjalna": 503}  # column centres

CROPS = {
    "zetony": (6, 40, 120, 555, 790),
    "zetony-poszukiwan-przeglad": (6, 40, 152, 555, 256),
    "zetony-armii": (6, 40, 260, 555, 362),
    "zetony-pierscieni-elfow": (6, 40, 366, 375, 470),
    "znacznik-zepsucia": (6, 375, 366, 555, 470),
    "zetony-towarzyszy": (6, 40, 474, 300, 568),
    "znacznik-postepow": (6, 300, 474, 555, 568),
    "znaczniki-polityki-przeglad": (6, 40, 571, 555, 676),
    "znaczniki-kontroli": (6, 40, 679, 205, 784),
    "znaczniki-punktow-zwyciestwa": (6, 205, 679, 375, 784),
    "zetony-gracza-prowadzacego": (6, 375, 679, 555, 784),
    "figurki": (7, 40, 112, 555, 806),
    "narody": (9, 40, 262, 555, 805),
    "legenda-mapy": (10, 40, 125, 275, 745),
    "fortyfikacja": (10, 370, 672, 490, 752),
    "wioski": (11, 35, 218, 290, 316),
    "miasta": (11, 35, 362, 290, 458),
    "twierdze": (11, 35, 570, 290, 703),
    "plansza-lewa": (12, 40, 125, 595, 770),
    "plansza-prawa": (13, 0, 125, 555, 770),
    "przygotowanie-lewa": (16, 40, 125, 595, 790),
    "przygotowanie-prawa": (17, 0, 125, 555, 790),
    "kosci-akcji": (19, 40, 85, 555, 365),
    "pierscienie-elfow": (21, 310, 675, 555, 790),
    "karty-wydarzen": (23, 40, 245, 555, 782),
    "karty-postaci": (25, 40, 125, 555, 790),
    "znaczniki-kontroli-cien-wl": (33, 310, 618, 555, 735),
    "znaczniki-polityki": (35, 310, 243, 555, 820),
    "druzyna-pierscienia": (36, 300, 110, 555, 470),
    "zetony-poszukiwan": (40, 40, 575, 290, 790),
    "tor-mordoru": (43, 305, 554, 555, 795),
    "punkty-zwyciestwa": (44, 310, 125, 555, 335),
    "znaczniki-pz": (44, 310, 655, 555, 770),
    "symbole-graczy": (46, 305, 172, 560, 297),
}
for key, x in DICE_X.items():
    CROPS[f"kosc-wl-{key}"] = (19, x - 23, 137, x + 23, 182)
    CROPS[f"kosc-cien-{key}"] = (19, x - 23, 247, x + 23, 287)


def main(pdf: str) -> None:
    OUT.mkdir(exist_ok=True)
    s = DPI / 72
    for name, (page, x0, y0, x1, y1) in CROPS.items():
        base = OUT / name
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-f", str(page), "-l", str(page),
             "-x", str(round(x0 * s)), "-y", str(round(y0 * s)),
             "-W", str(round((x1 - x0) * s)), "-H", str(round((y1 - y0) * s)),
             "-png", "-singlefile", pdf, str(base)],
            check=True,
        )
        png = base.with_suffix(".png")
        if png.stat().st_size > JPEG_ABOVE_BYTES:
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "82",
                            str(png), "--out", str(base.with_suffix(".jpg"))],
                           check=True, capture_output=True)
            png.unlink()
    print("ok:", len(CROPS), "images")


if __name__ == "__main__":
    main(sys.argv[1])
