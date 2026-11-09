"""Crops images from the PDF rulebooks into the img/ folder.

Requires poppler (pdftoppm) and macOS (sips, to convert large images to JPEG).
Coordinates are in PDF points: (page, x0, y0, x1, y1) or (page, x0, y0, x1, y1, dpi).
Page sizes: base rulebook 584 x 754 pt; Gadzi Grobowiec 756 x 543 pt (two pages per sheet);
Słudzy Czarnej Bramy 401 x 543 pt. Use `pdftotext -bbox-layout` to find exact text positions.
Image names stay Polish because the files in src/ refer to them by name.
Usage: python3 tools/crop_images.py /path/to/folder-with-the-pdfs [name ...]
    With names, only those images are cropped.
"""
import subprocess
import sys
from pathlib import Path

# rulebook key -> file name of the Polish PDF
PDFS = {
    "base": "podstawka.pdf",
    "tomb": "Gadzi_grobowiec_instrukcja_PL.pdf",
    "gate": "czarna_brama_instrukcja_PL.pdf",
}

DPI = 170
ICON_DPI = 300  # small inline icons are cropped sharper
JPEG_ABOVE_BYTES = 250_000
OUT = Path(__file__).resolve().parent.parent / "img"

# rulebook key -> image name -> crop box
CROPS = {
    "base": {
        "komponenty": (3, 15, 50, 545, 680),
        "arkusze-wladcow": (3, 15, 290, 368, 680),
        "obszar-gry": (5, 40, 60, 540, 697),
        "zdolnosci-karty": (7, 386, 286, 531, 503),
        "karta-wplywow": (8, 380, 78, 525, 304),
        "przyklad-ataku": (9, 52, 392, 535, 630),
        "horda-kompatybilnosc": (10, 63, 186, 522, 342),
        "horda-przyklad": (10, 120, 532, 464, 622),
        "horda-rozszerzenie": (11, 124, 176, 458, 322),
        "horda-zdolnosci": (11, 63, 402, 522, 490),
        "nawiedzenie": (12, 74, 500, 494, 636),
        "zetony-nawiedzenia": (14, 98, 620, 254, 686),
        "frakcje": (15, 60, 132, 278, 314),
        # inline icons
        "frakcja-bestie": (15, 70, 137, 126, 200, ICON_DPI),
        "frakcja-smiertelnicy": (15, 180, 137, 243, 200, ICON_DPI),
        "frakcja-duchy": (15, 72, 226, 126, 290, ICON_DPI),
        "frakcja-nieumarli": (15, 186, 226, 243, 290, ICON_DPI),
        "moc": (16, 92, 183, 107.5, 200, ICON_DPI),
        "moneta": (16, 112, 295, 127, 312, ICON_DPI),
        "pancerz": (16, 115, 443, 128.5, 460, ICON_DPI),
        "regeneracja": (16, 376, 95, 393.5, 112, ICON_DPI),
        "symbol-polecane": (4, 248.5, 309.5, 264.5, 326, ICON_DPI),
    },
    "tomb": {
        "gg-wladcy": (1, 50, 335, 351, 415),
        "gg-arkusz-sobka": (1, 430, 217, 640, 368),
        "gg-komponenty": (2, 402, 80, 716, 390),
        "gg-zetony-terroru": (2, 405, 130, 570, 171),
        "gg-ulica-przystanie": (2, 49, 126, 352, 221),
        "gg-kafle-przystani": (2, 405, 305, 595, 386),
        "gg-opactwo-westminster": (2, 134, 436, 273, 506),
    },
    "gate": {},
}


def jobs() -> dict[str, tuple[str, tuple]]:
    """image name -> (rulebook key, crop box)"""
    out: dict[str, tuple[str, tuple]] = {}
    for book, crops in CROPS.items():
        for name, box in crops.items():
            if name in out:
                sys.exit(f"duplicate image name: {name}")
            out[name] = (book, box)
    return out


def crop(pdf: str, base: Path, box: tuple) -> None:
    page, x0, y0, x1, y1, *rest = box
    dpi = rest[0] if rest else DPI
    s = dpi / 72
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page),
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


def main(folder: str, only: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    todo = jobs()
    for name in only:
        if name not in todo:
            sys.exit(f"unknown image: {name}")
    for name, (book, box) in todo.items():
        if only and name not in only:
            continue
        for old in (OUT / f"{name}.png", OUT / f"{name}.jpg"):
            old.unlink(missing_ok=True)  # a re-crop may change PNG <-> JPEG
        crop(str(Path(folder) / PDFS[book]), OUT / name, box)
    print("ok:", len(only) if only else len(todo), "images")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
