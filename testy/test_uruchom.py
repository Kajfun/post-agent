"""Sprawdza bootstrap odpalany przez przyciski."""

import os
import subprocess
import sys
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KORZEN / "narzedzia"))
import uruchom  # noqa: E402


def main() -> int:
    bledy = []

    def sprawdz(w, opis):
        print(f"  {'OK  ' if w else 'BLAD'}  {opis}")
        if not w:
            bledy.append(opis)

    def wywolaj(*args):
        return subprocess.run(
            [sys.executable, str(KORZEN / "narzedzia" / "uruchom.py"), *args],
            capture_output=True, text=True, cwd=KORZEN,
        )

    print("\n--- rozpoznawanie narzedzi ---")
    w = wywolaj("nie-ma-takiego")
    sprawdz(w.returncode == 1, "nieznane narzedzie konczy sie kodem 1")
    sprawdz("Dostepne:" in w.stderr, "podpowiada, co jest dostepne")

    w = wywolaj("publikuj")
    sprawdz(w.returncode == 1, "brakujacy plik narzedzia konczy sie kodem 1")
    sprawdz("jeszcze nie istnieje" in w.stderr,
            "mowi wprost, ze narzedzia jeszcze nie ma")
    sprawdz("Traceback" not in w.stderr, "bez sladu stosu w twarz uzytkownika")

    w = wywolaj("--help")
    sprawdz(w.returncode == 0, "--help konczy sie kodem 0")
    for n in uruchom.NARZEDZIA:
        if n not in w.stdout:
            sprawdz(False, f"--help wymienia '{n}'")
            break
    else:
        sprawdz(True, "--help wymienia wszystkie narzedzia")

    print("\n--- sciezki ---")
    py = uruchom.python_srodowiska()
    oczekiwany = "python.exe" if os.name == "nt" else "python"
    sprawdz(py.name == oczekiwany, f"python srodowiska nazywa sie {oczekiwany}")
    sprawdz(uruchom.SRODOWISKO.parent == KORZEN, "srodowisko lezy w katalogu projektu")

    print("\n--- narzedzia wskazuja na istniejace pliki ---")
    for nazwa, (plik, _) in uruchom.NARZEDZIA.items():
        istnieje = (KORZEN / "narzedzia" / plik).is_file()
        if nazwa == "publikuj":
            sprawdz(not istnieje, "publikuj celowo jeszcze nie istnieje")
        else:
            sprawdz(istnieje, f"'{nazwa}' wskazuje na istniejacy {plik}")

    print("\n--- czytelny blad zamiast sladu stosu ---")
    log = KORZEN / "ostatni-blad.txt"
    log.unlink(missing_ok=True)
    kod = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import uruchom; "
         "uruchom.uruchom([sys.executable, '-c', 'raise SystemExit(3)'], "
         "'probny krok', rada='Tak wyglada rada.')"
         % str(KORZEN / "narzedzia")],
        capture_output=True, text=True, cwd=KORZEN,
    )
    sprawdz(kod.returncode == 1, "nieudany krok konczy prace kodem 1")
    sprawdz("Tak wyglada rada." in kod.stderr, "rada trafia do uzytkownika")
    sprawdz(log.is_file(), "szczegoly ladowa w ostatni-blad.txt")
    log.unlink(missing_ok=True)

    print("\n--- wykrywanie przegladarki ---")
    wynik = uruchom.przegladarka_jest(uruchom.python_srodowiska())
    sprawdz(isinstance(wynik, bool), f"sonda zwraca prawde albo falsz (dala {wynik})")

    print("\n--- pliki startowe ---")
    start = KORZEN / "start"
    for nazwa in ["_uruchom.bat", "_uruchom.sh",
                  "1. Rozpoznaj formularz.bat", "1. Rozpoznaj formularz.command",
                  "2. Zatwierdz posty.bat", "2. Zatwierdz posty.command"]:
        sprawdz((start / nazwa).is_file(), f"jest {nazwa}")
    for nazwa in ["_uruchom.sh", "1. Rozpoznaj formularz.command",
                  "2. Zatwierdz posty.command"]:
        sprawdz(os.access(start / nazwa, os.X_OK), f"{nazwa} jest wykonywalny")
    for nazwa in ["_uruchom.bat", "1. Rozpoznaj formularz.bat"]:
        sprawdz(b"\r\n" in (start / nazwa).read_bytes(),
                f"{nazwa} ma zakonczenia linii Windows")

    print(f"\n{'=' * 50}")
    if bledy:
        print(f"BLEDOW: {len(bledy)}")
        for b in bledy:
            print(f"  - {b}")
        return 1
    print("Wszystko przeszlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
