#!/usr/bin/env python3
"""Wyciaga najlepsze klatki z nagran i zapisuje je jako zdjecia.

Model nie przyjmuje plikow wideo. Przyjmuje obrazy, wiec z nagrania trzeba
najpierw wyjac klatki. Okazuje sie to zaleta: w dwudziestosekundowym nagraniu
jest zwykle lepszy kadr niz na ktorymkolwiek zdjeciu zrobionym w pospiechu.

Skrypt probkuje nagranie, ocenia ostrosc kazdej klatki, odrzuca prawie
identyczne i zapisuje najlepsze jako zwykle JPEG. Dalej ida tam, gdzie
zdjecia: do oceny przez model.

Uzycie:
    python3 narzedzia/klatki.py ~/zdjecia/czwartek/nagranie.mp4
    python3 narzedzia/klatki.py ~/zdjecia/czwartek --ile 2   # caly katalog
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Brakuje bibliotek. Zainstaluj: pip install Pillow numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from przygotuj_zdjecia import (  # noqa: E402
    PROG_OSTROSCI, dhash, odleglosc, ostrosc, wczytaj_szary,
)

# Przy klatkach z jednego nagrania prog duplikatu musi byc OSTRZEJSZY niz przy
# zdjeciach: sasiednie klatze sa z natury podobne, bo to ta sama sala i to samo
# kadrowanie. Przy progu jak dla zdjec caly material zwinalby sie do jednej
# klatki. Rownosc kadrow pilnuje przede wszystkim podzial na segmenty czasowe.
PROG_DUPLIKATU_KLATEK = 3

ROZSZERZENIA = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp"}


def sprawdz_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        sys.exit(
            "Brakuje ffmpeg. Zainstaluj:\n"
            "    Ubuntu/Debian:  sudo apt install ffmpeg\n"
            "    macOS:          brew install ffmpeg"
        )


def dlugosc(plik: Path) -> float:
    """Dlugosc nagrania w sekundach; 0.0 gdy ffprobe nie potrafi jej podac."""
    wynik = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(plik)],
        capture_output=True, text=True,
    )
    try:
        return float(wynik.stdout.strip())
    except ValueError:
        return 0.0


def wyjmij_klatki(plik: Path, katalog: Path, na_sekunde: float) -> list[Path]:
    """Probkuje nagranie z zadana czestoscia. Zwraca sciezki do klatek."""
    katalog.mkdir(parents=True, exist_ok=True)
    wynik = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(plik),
         "-vf", f"fps={na_sekunde}", "-q:v", "2",
         str(katalog / "klatka_%04d.jpg")],
        capture_output=True, text=True,
    )
    if wynik.returncode != 0:
        print(f"  ffmpeg nie poradzil sobie z {plik.name}: "
              f"{wynik.stderr.strip()[:200]}", file=sys.stderr)
        return []
    return sorted(katalog.glob("klatka_*.jpg"))


def wybierz_najlepsze(klatki: list[Path], ile: int) -> list[tuple[Path, float]]:
    """Najostrzejsza klatka z kazdego odcinka nagrania.

    Nie wystarczy wziac trzech najostrzejszych klatek w ogole, bo najostrzejsze
    sa zwykle tuz obok siebie i dostalibysmy trzy razy ten sam moment. Dlatego
    nagranie dzielimy na tyle rownych odcinkow, ile klatek chcemy, i z kazdego
    bierzemy najlepsza. Klatki pochodza wtedy z roznych momentow zajec.

    Klatki rozmazane odrzucamy tym samym progiem co zdjecia: pusty slot jest
    lepszy niz rozmazany kadr dobrany tylko po to, zeby go zapelnic.
    """
    ocenione = []
    for k in klatki:  # klatki przychodza w kolejnosci czasowej
        szary = wczytaj_szary(k)
        if szary is None:
            continue
        h = dhash(k)
        if h is None:
            continue
        ocenione.append((k, ostrosc(szary), h))

    if not ocenione:
        return []

    wybrane: list[tuple[Path, float]] = []
    hashe: list[int] = []
    liczba_odcinkow = min(ile, len(ocenione))

    for nr in range(liczba_odcinkow):
        od = nr * len(ocenione) // liczba_odcinkow
        do = (nr + 1) * len(ocenione) // liczba_odcinkow
        odcinek = sorted(ocenione[od:do], key=lambda t: -t[1])

        for sciezka, ostr, h in odcinek:
            if ostr < PROG_OSTROSCI:
                break  # odcinek posortowany malejaco, dalsze sa jeszcze gorsze
            if any(odleglosc(h, poprz) <= PROG_DUPLIKATU_KLATEK for poprz in hashe):
                continue
            wybrane.append((sciezka, ostr))
            hashe.append(h)
            break

    return wybrane


def przetworz(plik: Path, wyjscie: Path, ile: int, maks_px: int) -> int:
    czas = dlugosc(plik)
    opis_czasu = f"{czas:.0f} s" if czas else "dlugosc nieznana"
    print(f"\n{plik.name} ({opis_czasu})")

    # Przy krotkim nagraniu probkujemy gesciej, przy dlugim rzadziej, zeby nie
    # wyciagac setek klatek z kilkuminutowego filmu.
    na_sekunde = 2.0 if czas and czas <= 15 else (1.0 if czas and czas <= 60 else 0.5)

    with tempfile.TemporaryDirectory() as tmp:
        klatki = wyjmij_klatki(plik, Path(tmp), na_sekunde)
        if not klatki:
            print("  nie udalo sie wyjac zadnej klatki")
            return 0
        print(f"  wyjetych klatek: {len(klatki)}")

        najlepsze = wybierz_najlepsze(klatki, ile)
        if not najlepsze:
            print("  zadna klatka nie nadaje sie do oceny")
            return 0

        wyjscie.mkdir(parents=True, exist_ok=True)
        for i, (sciezka, ostr) in enumerate(najlepsze, 1):
            cel = wyjscie / f"{plik.stem}_klatka{i}.jpg"
            with Image.open(sciezka) as img:
                img = img.convert("RGB")
                img.thumbnail((maks_px, maks_px), Image.Resampling.LANCZOS)
                img.save(cel, "JPEG", quality=85, optimize=True)
            print(f"  {cel.name:<32} ostrosc {ostr:>7.0f}")
    return len(najlepsze)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Wyciaga najlepsze klatki z nagran i zapisuje jako zdjecia."
    )
    p.add_argument("sciezka", type=Path, help="plik wideo albo katalog z nagraniami")
    p.add_argument("--ile", type=int, default=3,
                   help="ile klatek z jednego nagrania (domyslnie 3)")
    p.add_argument("--maks-px", type=int, default=1024,
                   help="dluzszy bok zapisanej klatki (domyslnie 1024)")
    args = p.parse_args()

    sprawdz_ffmpeg()

    if args.sciezka.is_file():
        nagrania = [args.sciezka]
        katalog = args.sciezka.parent
    elif args.sciezka.is_dir():
        nagrania = sorted(
            s for s in args.sciezka.iterdir()
            if s.is_file() and s.suffix.lower() in ROZSZERZENIA
        )
        katalog = args.sciezka
    else:
        print(f"Nie ma takiej sciezki: {args.sciezka}", file=sys.stderr)
        return 1

    if not nagrania:
        print(f"Brak nagran w {args.sciezka}", file=sys.stderr)
        return 1

    wyjscie = katalog / "z-nagran"
    razem = sum(przetworz(n, wyjscie, args.ile, args.maks_px) for n in nagrania)

    if razem:
        print(f"\nZapisanych klatek: {razem}, w {wyjscie}")
        print("Traktuj je dalej jak zwykle zdjecia: ocenia je model.")
    else:
        print("\nNic nie udalo sie wyciagnac.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
