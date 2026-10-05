#!/usr/bin/env python3
"""Przeglad zdjec i tekst postu przez API, poza limitem abonamentu.

Rozliczane od tokenow, nie z puli Claude Pro/Max. Przy czterech grupach
tygodniowo to rzad wielkosci zlotowki miesiecznie na Haiku i okolo czterech
na Opusie.

Zachowuje cztery kroki z zasad i zatrzymanie po kazdym: po kazdym kroku mozesz
wpisac poprawke albo wcisnac Enter, zeby isc dalej.

Uzycie:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 narzedzia/post.py ~/zdjecia/czwartek/do-wyslania --grupa "Mickiewicza czwartek"
    python3 narzedzia/post.py ... --model opus      # gdy chcesz ostrzejsza ocene zdjec
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("Brakuje SDK. Zainstaluj: pip install anthropic")

ZASADY = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "posty" / "SKILL.md"

MODELE = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

# USD za milion tokenow, do policzenia kosztu przebiegu.
CENNIK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

TYPY = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
}

KROKI = [
    (
        "1. PRZEGLAD ZDJEC",
        "Przejrzyj kazde zdjecie osobno, po kryteriach z sekcji ZDJECIA. "
        "Przy kazdym jedno zdanie: bierzemy czy nie i dlaczego. Odwoluj sie do "
        "numerow, ktore podalem przy zdjeciach. Grupe duplikatow skwituj jedna "
        "zbiorcza linijka. Badz bezwzgledny. Na koniec podaj, ile zdjec przeszlo. "
        "Na tym etapie nie wybieraj jeszcze zestawu i nie pisz tekstu.",
    ),
    (
        "2. WYBOR ZESTAWU",
        "Wybierz trzy, maksymalnie cztery zdjecia do postu, w kolejnosci zgodnej "
        "z przebiegiem zajec. Uzasadnij kazdy wybor jednym zdaniem, zebym mogl sie "
        "nie zgodzic. Przy zdjeciach wymagajacych kadrowania powiedz dokladnie, co "
        "wyciac. Nie pisz jeszcze tekstu postu.",
    ),
    (
        "3. TEKST POSTU",
        "Napisz tekst postu. Trzymaj sie wzoru i sekcji STYL. Pod tekstem podaj "
        "licznik znakow ze spacjami. Nie dodawaj nic poza tekstem i licznikiem.",
    ),
]


def wczytaj_zdjecia(katalog: Path) -> list[tuple[str, str, str]]:
    """Zwraca liste (nazwa, media_type, base64) posortowana po nazwie."""
    pliki = sorted(
        s for s in katalog.iterdir()
        if s.is_file() and s.suffix.lower() in TYPY
    )
    out = []
    for s in pliki:
        dane = base64.standard_b64encode(s.read_bytes()).decode()
        out.append((s.name, TYPY[s.suffix.lower()], dane))
    return out


def tresc_startowa(zdjecia, grupa: str, opis: str, polecenie: str) -> list[dict]:
    """Zdjecia numerowane, zeby model i instruktor mowili o tych samych kadrach.

    Polecenie pierwszego kroku doklejamy do tej samej wiadomosci, zeby nie
    wysylac dwoch wiadomosci roli "user" pod rzad.
    """
    bloki: list[dict] = [{
        "type": "text",
        "text": (
            f"Grupa: {grupa}\n\n"
            f"Co sie dzialo na zajeciach, wedlug instruktora:\n{opis}\n\n"
            f"Zdjecia z tych zajec, {len(zdjecia)} sztuk, ponumerowane:"
        ),
    }]
    for i, (nazwa, typ, dane) in enumerate(zdjecia, 1):
        bloki.append({"type": "text", "text": f"Zdjecie {i}: {nazwa}"})
        bloki.append({
            "type": "image",
            "source": {"type": "base64", "media_type": typ, "data": dane},
        })
    bloki.append({"type": "text", "text": polecenie})
    return bloki


def zapytaj(klient, model: str, system: list[dict], wiadomosci: list[dict]) -> tuple[str, object]:
    kwargs: dict = {
        "model": model,
        "max_tokens": 4000,
        "system": system,
        "messages": wiadomosci,
    }
    # Haiku 4.5 nie przyjmuje output_config.effort; nowsze modele tak.
    if model != "claude-haiku-4-5":
        kwargs["output_config"] = {"effort": "medium"}

    with klient.messages.stream(**kwargs) as strumien:
        odp = strumien.get_final_message()

    tekst = "".join(b.text for b in odp.content if b.type == "text")
    return tekst, odp.usage


def koszt(model: str, zuzycie_lista) -> float:
    we, wy = CENNIK.get(model, (0.0, 0.0))
    suma = 0.0
    for u in zuzycie_lista:
        wejscie = getattr(u, "input_tokens", 0) or 0
        wejscie += getattr(u, "cache_creation_input_tokens", 0) or 0
        czytane = getattr(u, "cache_read_input_tokens", 0) or 0
        suma += wejscie / 1e6 * we
        suma += czytane / 1e6 * we * 0.1   # odczyt z cache jest ok. 10% ceny
        suma += (getattr(u, "output_tokens", 0) or 0) / 1e6 * wy
    return suma


def main() -> int:
    p = argparse.ArgumentParser(description="Przeglad zdjec i tekst postu przez API.")
    p.add_argument("katalog", type=Path, help="katalog ze zdjeciami jednej grupy")
    p.add_argument("--grupa", required=True, help="nazwa grupy, np. 'Mickiewicza czwartek'")
    p.add_argument("--model", choices=sorted(MODELE), default="sonnet")
    p.add_argument("--opis", help="co sie dzialo; bez tego skrypt zapyta")
    args = p.parse_args()

    if not ZASADY.is_file():
        print(f"Nie znajduje zasad: {ZASADY}", file=sys.stderr)
        return 1
    if not args.katalog.is_dir():
        print(f"Nie ma takiego katalogu: {args.katalog}", file=sys.stderr)
        return 1

    zdjecia = wczytaj_zdjecia(args.katalog)
    if not zdjecia:
        print(f"Brak zdjec w {args.katalog}", file=sys.stderr)
        return 1

    opis = args.opis
    if not opis:
        print("Co sie dzialo na tych zajeciach? Podaj zadanie, zakonczenie")
        print("i cokolwiek nietypowego. Pusta linia konczy.\n")
        linie = []
        while (linia := input("> ")).strip():
            linie.append(linia)
        opis = "\n".join(linie)
    if not opis.strip():
        print("Bez opisu zajec nie da sie napisac postu.", file=sys.stderr)
        return 1

    model = MODELE[args.model]
    klient = anthropic.Anthropic()

    # Zasady sa identyczne przy kazdej grupie, wiec warto je cache'owac.
    system = [{
        "type": "text",
        "text": ZASADY.read_text(encoding="utf-8"),
        "cache_control": {"type": "ephemeral"},
    }]
    wiadomosci: list[dict] = [{
        "role": "user",
        "content": tresc_startowa(zdjecia, args.grupa, opis, KROKI[0][1]),
    }]
    zuzycie = []

    print(f"\nModel: {model}   Zdjec: {len(zdjecia)}   Grupa: {args.grupa}")

    for nr, (naglowek, polecenie) in enumerate(KROKI):
        print(f"\n{'=' * 64}\n{naglowek}\n{'=' * 64}\n")
        if nr:  # krok 1 jest juz wbudowany w wiadomosc startowa
            wiadomosci.append({"role": "user", "content": polecenie})

        while True:
            tekst, u = zapytaj(klient, model, system, wiadomosci)
            zuzycie.append(u)
            print(tekst)
            wiadomosci.append({"role": "assistant", "content": tekst})

            uwaga = input("\n[Enter = dalej, albo wpisz poprawke] > ").strip()
            if not uwaga:
                break
            wiadomosci.append({"role": "user", "content": uwaga})

    print(f"\n{'=' * 64}")
    print(f"Koszt tego przebiegu: {koszt(model, zuzycie):.4f} USD")
    print(
        "\nJesli cos poprawiales, przepisz poprawiona zasade do "
        f"{ZASADY.relative_to(ZASADY.parents[3])} zgodnie z krokiem 4."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
