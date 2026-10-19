#!/usr/bin/env python3
"""Przygotowuje srodowisko i odpala wybrane narzedzie.

Wolany przez pliki startowe (Start-*.bat / .command / .sh), zeby instruktor
nie musial znac terminala. Przy pierwszym uruchomieniu robi wszystko sam:
zaklada wlasne srodowisko Pythona obok projektu, dociaga biblioteki i, jesli
narzedzie tego potrzebuje, przegladarke. Przy kolejnych tylko sprawdza, czy
nic nie brakuje, i od razu startuje.

Uzycie:
    python3 narzedzia/uruchom.py rozpoznaj
    python3 narzedzia/uruchom.py przeglad posty.json
    python3 narzedzia/uruchom.py --sprawdz        # samo srodowisko, bez odpalania
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
SRODOWISKO = KORZEN / ".venv"

# nazwa polecenia -> (plik, czy potrzebuje przegladarki)
NARZEDZIA = {
    "rozpoznaj": ("rozpoznaj.py", True),
    "publikuj": ("publikuj.py", True),
    "przeglad": ("przeglad.py", False),
    "analiza": ("analiza.py", False),
    "zdjecia": ("przygotuj_zdjecia.py", False),
    "klatki": ("klatki.py", False),
}


def python_srodowiska() -> Path:
    if os.name == "nt":
        return SRODOWISKO / "Scripts" / "python.exe"
    return SRODOWISKO / "bin" / "python"


def uruchom(polecenie: list[str], opis: str, rada: str = "") -> None:
    print(f"  {opis}...", flush=True)
    wynik = subprocess.run(polecenie, capture_output=True, text=True)
    if wynik.returncode != 0:
        # Surowe wyjscie to zwykle sciana sladu stosu z Node albo pipa, w ktorej
        # nie da sie znalezc przyczyny. Pokazujemy rade po ludzku, a szczegoly
        # chowamy do pliku na wypadek, gdyby byly potrzebne.
        print(f"\nNie udalo sie: {opis}", file=sys.stderr)
        if rada:
            print(f"\n{rada}", file=sys.stderr)
        log = KORZEN / "ostatni-blad.txt"
        log.write_text(
            f"$ {' '.join(polecenie)}\n\n{wynik.stdout}\n{wynik.stderr}",
            encoding="utf-8",
        )
        print(f"\nSzczegoly techniczne: {log}", file=sys.stderr)
        raise SystemExit(1)


def przegladarka_jest(py: Path) -> bool:
    """Czy Playwright widzi juz chromium. Nie pobieramy tego, co jest."""
    sprawdzenie = (
        "import pathlib, sys\n"
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    sys.exit(0 if pathlib.Path(p.chromium.executable_path).exists() else 1)\n"
    )
    return subprocess.run(
        [str(py), "-c", sprawdzenie], capture_output=True
    ).returncode == 0


def przygotuj(potrzebna_przegladarka: bool) -> Path:
    py = python_srodowiska()

    if not py.exists():
        print("Pierwsze uruchomienie, przygotowuje srodowisko.")
        print("Potrwa to kilka minut. Nastepnym razem bedzie od razu.\n")
        uruchom([sys.executable, "-m", "venv", str(SRODOWISKO)],
                "tworze srodowisko Pythona")

    wymagania = KORZEN / "requirements.txt"
    brakuje = subprocess.run(
        [str(py), "-c", "import PIL, numpy, anthropic, playwright"],
        capture_output=True,
    ).returncode != 0
    if brakuje:
        uruchom([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                "aktualizuje pip")
        uruchom([str(py), "-m", "pip", "install", "--quiet", "-r", str(wymagania)],
                "instaluje biblioteki")

    if potrzebna_przegladarka and not przegladarka_jest(py):
        uruchom(
            [str(py), "-m", "playwright", "install", "chromium"],
            "pobieram przegladarke, okolo 150 MB",
            rada=(
                "Przegladarki nie udalo sie pobrac. Najczestsze powody:\n"
                "  brak polaczenia z internetem,\n"
                "  firma albo szkola blokuje cdn.playwright.dev,\n"
                "  za malo miejsca na dysku.\n\n"
                "Sprobuj z innej sieci, na przyklad z telefonu. Pobiera sie\n"
                "raz, potem dziala bez internetu do samego logowania."
            ),
        )

    return py


def main() -> int:
    argumenty = sys.argv[1:]

    if not argumenty or argumenty[0] in ("-h", "--help"):
        print(__doc__)
        print("Dostepne narzedzia: " + ", ".join(NARZEDZIA))
        return 0

    if argumenty[0] == "--sprawdz":
        py = przygotuj(potrzebna_przegladarka=True)
        wersja = subprocess.run([str(py), "--version"], capture_output=True, text=True)
        print(f"\nSrodowisko gotowe: {py}")
        print(f"Python: {wersja.stdout.strip()}")
        return 0

    nazwa, reszta = argumenty[0], argumenty[1:]
    if nazwa not in NARZEDZIA:
        print(f"Nie znam narzedzia '{nazwa}'.", file=sys.stderr)
        print("Dostepne: " + ", ".join(NARZEDZIA), file=sys.stderr)
        return 1

    plik, z_przegladarka = NARZEDZIA[nazwa]
    sciezka = KORZEN / "narzedzia" / plik
    if not sciezka.is_file():
        print(f"Narzedzie '{nazwa}' jeszcze nie istnieje ({plik}).", file=sys.stderr)
        return 1

    py = przygotuj(z_przegladarka)
    print()
    # Oddajemy sterowanie narzedziu: ma wlasne wejscie i wyjscie w terminalu.
    return subprocess.run([str(py), str(sciezka), *reszta], cwd=KORZEN).returncode


if __name__ == "__main__":
    raise SystemExit(main())
