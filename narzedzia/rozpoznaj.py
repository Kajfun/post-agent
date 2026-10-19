#!/usr/bin/env python3
"""Zrzuca strukture formularza "Nowy post grupowy", zeby dalo sie go wypelniac.

Uruchamiasz to RAZ. Skrypt otwiera przegladarke, ty logujesz sie recznie
i otwierasz okienko dodawania postu, a skrypt spisuje, jak nazywaja sie pola.
Bez tego trzeba by zgadywac selektory ze zrzutu ekranu, a zgadywanie oznacza
kilka rund poprawek.

Logowanie zostaje w profilu przegladarki na twoim dysku, wiec przy kolejnych
uruchomieniach nie bedziesz sie logowal. Haslo nigdzie nie jest zapisywane
przez ten skrypt.

Przygotowanie (raz):
    pip install playwright
    playwright install chromium

Uzycie:
    python3 narzedzia/rozpoznaj.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit(
        "Brakuje Playwrighta. Zainstaluj:\n"
        "    pip install playwright\n"
        "    playwright install chromium"
    )

ADRES = "https://app.akademiarobotyka.pl/aktualnosci"
PROFIL = Path.home() / ".akademia-profil"
WYNIK = Path("rozpoznanie")

# Zbieramy tylko to, co sluzy do trafienia w pole: etykiety, placeholdery,
# atrybuty dostepnosci i identyfikatory. Zadnych wartosci, ktore uzytkownik
# wpisal, zeby zrzut nie wyniosl przypadkiem danych.
SKRYPT = """
() => {
    const widoczny = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    const etykieta = (el) => {
        if (el.id) {
            const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (l) return l.innerText.trim();
        }
        const rodzic = el.closest('label');
        if (rodzic) return rodzic.innerText.trim();
        // MUI i podobne: etykieta jako rodzenstwo w tym samym kontenerze
        const box = el.closest('div');
        if (box) {
            const l = box.querySelector('label');
            if (l) return l.innerText.trim();
        }
        return null;
    };
    const opis = (el) => ({
        tag: el.tagName.toLowerCase(),
        typ: el.getAttribute('type'),
        etykieta: etykieta(el),
        placeholder: el.getAttribute('placeholder'),
        nazwa: el.getAttribute('name'),
        id: el.id || null,
        rola: el.getAttribute('role'),
        aria: el.getAttribute('aria-label'),
        testid: el.getAttribute('data-testid'),
        klasy: (el.className || '').toString().slice(0, 120),
        tekst: (el.innerText || '').trim().slice(0, 80) || null,
    });

    const pola = [...document.querySelectorAll('input, textarea, select')]
        .filter(widoczny).map(opis);
    const guziki = [...document.querySelectorAll('button, [role="button"]')]
        .filter(widoczny).map(opis);
    const przelaczniki = [...document.querySelectorAll('[role="switch"], input[type="checkbox"]')]
        .filter(widoczny).map(opis);

    const modal = document.querySelector('[role="dialog"], .MuiDialog-root, .modal');
    return {
        adres: location.href,
        tytul_strony: document.title,
        modal_znaleziony: !!modal,
        pola, guziki, przelaczniki,
        modal_html: modal ? modal.outerHTML.slice(0, 60000) : null,
    };
}
"""


def main() -> int:
    print(f"Profil przegladarki: {PROFIL}")
    print("Przy pierwszym uruchomieniu zaloguj sie recznie. Potem juz nie bedzie trzeba.\n")

    with sync_playwright() as pw:
        kontekst = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFIL),
            headless=False,
            viewport={"width": 1440, "height": 900},
        )
        strona = kontekst.pages[0] if kontekst.pages else kontekst.new_page()
        strona.goto(ADRES, wait_until="domcontentloaded")

        print("W otwartej przegladarce:")
        print("  1. zaloguj sie, jesli trzeba")
        print("  2. kliknij 'Dodaj post'")
        print("  3. poczekaj, az okienko sie w pelni pokaze")
        print("  4. wroc tutaj i nacisnij Enter\n")
        print("Nie wpisuj nic w pola. Zrzut nie zbiera wpisanych wartosci,")
        print("ale pusty formularz czyta sie najlepiej.\n")
        input("Enter, gdy okienko jest otwarte > ")

        dane = strona.evaluate(SKRYPT)

        WYNIK.mkdir(exist_ok=True)
        (WYNIK / "pola.json").write_text(
            json.dumps({k: v for k, v in dane.items() if k != "modal_html"},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if dane.get("modal_html"):
            (WYNIK / "modal.html").write_text(dane["modal_html"], encoding="utf-8")
        strona.screenshot(path=str(WYNIK / "ekran.png"), full_page=False)

        print(f"\nOkienko znalezione: {'tak' if dane['modal_znaleziony'] else 'NIE'}")
        print(f"Pol: {len(dane['pola'])}   guzikow: {len(dane['guziki'])}   "
              f"przelacznikow: {len(dane['przelaczniki'])}")
        print("\nPola, ktore widze:")
        for p in dane["pola"]:
            etyk = p["etykieta"] or p["placeholder"] or p["aria"] or p["nazwa"] or "?"
            print(f"  {p['tag']:<9} {etyk}")

        if not dane["modal_znaleziony"]:
            print("\nNie znalazlem okienka. Moze nie bylo otwarte albo ma inna budowe.")
            print("Zrzut ekranu i tak jest zapisany, przyslij go razem z plikami.")

        print(f"\nZapisane w katalogu: {WYNIK.resolve()}")
        print("Przyslij mi pola.json, modal.html i ekran.png.")
        kontekst.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
