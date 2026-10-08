#!/usr/bin/env python3
"""Wstepna selekcja zdjec z zajec, zanim zobaczy je model.

Robi trzy rzeczy, ktorych nie trzeba placic modelowi:
  1. wylapuje duplikaty (prawie identyczne ujecia) i zostawia z grupy to ostre
  2. wylapuje zdjecia rozmazane, ciemne i przeswietlone
  3. zmniejsza to, co zostalo, do rozmiaru, na ktorym model i tak pracuje

Dzieki temu do modelu idzie osiem sensownych zdjec zamiast czterdziestu,
w rozmiarze ok. 3x tanszym. Reszta kryteriow (dziecko na krzesle, kartka
z nazwiskami, balagan) wymaga patrzenia i zostaje dla modelu.

Uzycie:
    python3 narzedzia/przygotuj_zdjecia.py ~/zdjecia/czwartek
    python3 narzedzia/przygotuj_zdjecia.py ~/zdjecia/czwartek --maks-px 1024

Wynik laduje w podkatalogu `do-wyslania/` obok zdjec zrodlowych.
Nic nie jest kasowane.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError:
    sys.exit(
        "Brakuje bibliotek. Zainstaluj je poleceniem:\n"
        "    pip install Pillow numpy"
    )

ROZSZERZENIA = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# Progi sa celowo LAGODNE i nie powinny byc zaostrzane.
#
# Ten skrypt nie jest selekcja, tylko odsiewem oczywistosci. Ocena nalezy do
# modelu, a model kosztuje grosze: przy czterech grupach tygodniowo to rzad
# wielkosci zlotowki miesiecznie. Nie ma wiec zadnego powodu, zeby ryzykowac
# wyrzuceniem dobrego zdjecia dla oszczednosci ulamka groszа. Zdjecie
# watpliwe ZAWSZE przechodzi dalej.
#
# Realna wartosc tego skryptu to duplikaty: piec wariantow jednego ujecia
# instruktor widzi szybciej niz model, a ich odsianie nic nie kosztuje.
# Rozmycie i jasnosc to tylko te przypadki, ktore sa bezdyskusyjne.
PROG_OSTROSCI = 60.0       # wariancja laplasjanu; nizej = rozmazane bezdyskusyjnie
PROG_CIEMNOSCI = 35.0      # srednia jasnosc 0-255; nizej = prawie czarne
PROG_PRZESWIETLENIA = 235.0  # srednia jasnosc; wyzej = prawie biale
PROG_DUPLIKATU = 8         # odleglosc Hamminga miedzy hashami; nizej = duplikat


def wczytaj_szary(sciezka: Path, bok: int = 512) -> np.ndarray | None:
    """Zwraca zdjecie jako tablice odcieni szarosci albo None, gdy sie nie da."""
    try:
        with Image.open(sciezka) as img:
            img = img.convert("L")
            img.thumbnail((bok, bok), Image.Resampling.LANCZOS)
            return np.asarray(img, dtype=np.float64)
    except Exception:
        return None


def ostrosc(szary: np.ndarray) -> float:
    """Wariancja laplasjanu. Im wyzej, tym ostrzejsze zdjecie."""
    jadro = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    # splot bez scipy: sumujemy przesuniete kopie tablicy
    wynik = np.zeros_like(szary)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            waga = jadro[dy + 1, dx + 1]
            if waga:
                wynik += waga * np.roll(np.roll(szary, dy, axis=0), dx, axis=1)
    return float(wynik[1:-1, 1:-1].var())


def dhash(sciezka: Path, bok: int = 8) -> int | None:
    """Percepcyjny hash roznicowy. Prawie identyczne ujecia daja bliskie hashe."""
    try:
        with Image.open(sciezka) as img:
            maly = img.convert("L").resize((bok + 1, bok), Image.Resampling.LANCZOS)
    except Exception:
        return None
    piksele = np.asarray(maly, dtype=np.int16)
    bity = piksele[:, 1:] > piksele[:, :-1]
    wartosc = 0
    for bit in bity.flatten():
        wartosc = (wartosc << 1) | int(bit)
    return wartosc


def odleglosc(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


class Zdjecie:
    def __init__(self, sciezka: Path):
        self.sciezka = sciezka
        self.powod: str | None = None
        self.grupa: int | None = None
        szary = wczytaj_szary(sciezka)
        if szary is None:
            self.ostrosc = 0.0
            self.jasnosc = 0.0
            self.hash = None
            self.powod = "nie da sie otworzyc"
            return
        self.ostrosc = ostrosc(szary)
        self.jasnosc = float(szary.mean())
        self.hash = dhash(sciezka)

    @property
    def nazwa(self) -> str:
        return self.sciezka.name


def oznacz_jakosc(zdjecia: list[Zdjecie], prog_ostrosci: float) -> None:
    """Kolejnosc testow ma znaczenie.

    Zdjecie ciemne albo przeswietlone ma z definicji maly kontrast, a wiec
    niska wariancje laplasjanu. Gdyby ostrosc sprawdzac pierwsza, kazde takie
    zdjecie raportowaloby sie jako "rozmazane" i instruktor dostawalby mylacy
    powod odrzucenia. Dlatego najpierw jasnosc, potem ostrosc.
    """
    for z in zdjecia:
        if z.powod:
            continue
        if z.jasnosc < PROG_CIEMNOSCI:
            z.powod = f"za ciemne (jasnosc {z.jasnosc:.0f} < {PROG_CIEMNOSCI:.0f})"
        elif z.jasnosc > PROG_PRZESWIETLENIA:
            z.powod = f"przeswietlone (jasnosc {z.jasnosc:.0f} > {PROG_PRZESWIETLENIA:.0f})"
        elif z.ostrosc < prog_ostrosci:
            z.powod = f"rozmazane (ostrosc {z.ostrosc:.0f} < {prog_ostrosci:.0f})"


def pogrupuj_duplikaty(zdjecia: list[Zdjecie]) -> None:
    """Laczy prawie identyczne ujecia w grupy; przezywa najostrzejsze."""
    kandydaci = [z for z in zdjecia if not z.powod and z.hash is not None]
    numer_grupy = 0
    for i, z in enumerate(kandydaci):
        if z.grupa is not None:
            continue
        podobne = [z]
        for inny in kandydaci[i + 1:]:
            if inny.grupa is None and odleglosc(z.hash, inny.hash) <= PROG_DUPLIKATU:
                podobne.append(inny)
        if len(podobne) == 1:
            continue
        numer_grupy += 1
        najlepsze = max(podobne, key=lambda s: s.ostrosc)
        for s in podobne:
            s.grupa = numer_grupy
            if s is not najlepsze:
                s.powod = f"duplikat ujecia {najlepsze.nazwa} (grupa {numer_grupy})"


def zmniejsz(zrodlo: Path, cel: Path, maks_px: int) -> int:
    """Zapisuje zmniejszona kopie. Zwraca szacowana liczbe tokenow."""
    with Image.open(zrodlo) as img:
        img = img.convert("RGB")
        img.thumbnail((maks_px, maks_px), Image.Resampling.LANCZOS)
        cel.parent.mkdir(parents=True, exist_ok=True)
        img.save(cel, "JPEG", quality=85, optimize=True)
        return round(img.width * img.height / 750)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Wstepna selekcja i zmniejszenie zdjec z zajec."
    )
    p.add_argument("katalog", type=Path, help="katalog ze zdjeciami z jednej grupy")
    p.add_argument(
        "--maks-px", type=int, default=1024,
        help="dluzszy bok po zmniejszeniu (domyslnie 1024)",
    )
    p.add_argument(
        "--prog-ostrosci", type=float, default=PROG_OSTROSCI,
        help=(
            f"ponizej tej wartosci zdjecie uznajemy za rozmazane "
            f"(domyslnie {PROG_OSTROSCI:.0f}). Wartosc zalezy od aparatu "
            f"i swiatla w sali, patrz --kalibruj"
        ),
    )
    p.add_argument(
        "--kalibruj", action="store_true",
        help="tylko wypisz ostrosc i jasnosc kazdego zdjecia, nic nie odrzucaj",
    )
    p.add_argument(
        "--wszystko", action="store_true",
        help="skopiuj takze odrzucone, do recznego przejrzenia",
    )
    args = p.parse_args()

    if not args.katalog.is_dir():
        print(f"Nie ma takiego katalogu: {args.katalog}", file=sys.stderr)
        return 1

    pliki = sorted(
        s for s in args.katalog.iterdir()
        if s.is_file() and s.suffix.lower() in ROZSZERZENIA
    )
    if not pliki:
        print(f"Brak zdjec w {args.katalog}", file=sys.stderr)
        return 1

    print(f"Czytam {len(pliki)} zdjec z {args.katalog}\n")
    zdjecia = [Zdjecie(s) for s in pliki]

    if args.kalibruj:
        print("Tryb kalibracji. Nic nie jest odrzucane ani zapisywane.\n")
        print(f"{'plik':<32}{'ostrosc':>10}{'jasnosc':>10}")
        for z in sorted(zdjecia, key=lambda s: s.ostrosc):
            print(f"{z.nazwa:<32}{z.ostrosc:>10.0f}{z.jasnosc:>10.1f}")
        print(
            "\nObejrzyj zdjecia i znajdz granice miedzy ostrymi a rozmazanymi. "
            "\nTa liczba to twoj --prog-ostrosci."
        )
        return 0

    oznacz_jakosc(zdjecia, args.prog_ostrosci)
    pogrupuj_duplikaty(zdjecia)

    przeszly = [z for z in zdjecia if not z.powod]
    odpadly = [z for z in zdjecia if z.powod]

    wyjscie = args.katalog / "do-wyslania"
    tokeny = 0
    for z in sorted(przeszly, key=lambda s: s.nazwa):
        tokeny += zmniejsz(z.sciezka, wyjscie / z.nazwa, args.maks_px)
    if args.wszystko:
        for z in odpadly:
            if z.powod != "nie da sie otworzyc":
                zmniejsz(z.sciezka, wyjscie / "odrzucone" / z.nazwa, args.maks_px)

    if odpadly:
        print(f"Odpadlo mechanicznie: {len(odpadly)}")
        for z in sorted(odpadly, key=lambda s: s.nazwa):
            print(f"  {z.nazwa:<28} {z.powod}")
        print()

    print(f"Zostaje do oceny: {len(przeszly)}")
    for z in sorted(przeszly, key=lambda s: -s.ostrosc):
        print(f"  {z.nazwa:<28} ostrosc {z.ostrosc:>6.0f}  jasnosc {z.jasnosc:>5.1f}")

    przed = len(pliki) * 2460  # pelnowymiarowe zdjecie z telefonu
    print(f"\nZapisane w: {wyjscie}")
    print(f"Szacunkowo {tokeny} tokenow zamiast {przed} ({przed / max(tokeny, 1):.1f}x mniej)")

    if len(przeszly) < 3:
        print(
            "\nUWAGA: zostaly mniej niz trzy zdjecia. Zgodnie z zasadami nie "
            "dobieraj z odrzuconych na sile, tylko zdecyduj swiadomie."
        )
    if odpadly:
        print(
            "\nJesli cokolwiek odpadlo niesprawiedliwie, uruchom z --wszystko "
            "(odrzucone laduja w podkatalogu) albo podnies --prog-ostrosci."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
