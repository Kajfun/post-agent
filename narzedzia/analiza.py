#!/usr/bin/env python3
"""Jedno wywolanie API, ktore robi caly przeglad i pisze tekst postu.

To jest rdzen uzywany przez kazdy interfejs: bota na Telegramie, strone,
skrypt w terminalu. Interfejs tylko zbiera zdjecia i opis, wola `przeanalizuj`
i formatuje wynik.

Dlaczego jedno wywolanie, a nie trzy kroki z rozmowy:

    W rozmowie zdjecia sa wysylane od nowa przy kazdym kroku, wiec trzy kroki
    to trzykrotny koszt zdjec, a zdjecia sa calym kosztem. Jedno wywolanie ze
    strukturalna odpowiedzia daje to samo trzy razy taniej i w jednej rundzie.
    Instruktor dostaje wszystko naraz i poprawia jedna wiadomoscia, co na
    telefonie jest wygodniejsze niz cztery zatrzymania.

Uzycie jako biblioteka:

    from analiza import przeanalizuj, Zdjecie
    wynik = przeanalizuj(zdjecia, grupa="Mickiewicza czwartek", opis="...")

Uzycie z terminala:

    export ANTHROPIC_API_KEY=sk-ant-...
    python3 narzedzia/analiza.py ~/zdjecia/czwartek --grupa "Czwartek" --opis "..."
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from dataclasses import dataclass
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

CENNIK = {  # USD za milion tokenow: (wejscie, wyjscie)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

TYPY = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
}

SCHEMAT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["zdjecia", "zestaw", "tekst", "znakow", "pytania", "wymaga_oka"],
    "properties": {
        "zdjecia": {
            "type": "array",
            "description": "Werdykt dla KAZDEGO otrzymanego zdjecia, takze odrzuconego.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["numer", "decyzja", "powod"],
                "properties": {
                    "numer": {"type": "integer"},
                    "decyzja": {"type": "string", "enum": ["dopuszczone", "odrzucone"]},
                    "powod": {
                        "type": "string",
                        "description": "Jedno zdanie. Przy odrzuceniu konkretny powod, "
                                       "zeby instruktor wiedzial, co poprawic.",
                    },
                    "kadrowanie": {
                        "type": ["string", "null"],
                        "description": "Co wyciac, jesli zdjecie tego wymaga, inaczej null.",
                    },
                    "duplikat_do": {
                        "type": ["integer", "null"],
                        "description": "Numer lepszego ujecia z tej samej grupy duplikatow.",
                    },
                },
            },
        },
        "zestaw": {
            "type": "array",
            "description": "Trzy, maksymalnie cztery numery zdjec, w kolejnosci do postu.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["numer", "uzasadnienie"],
                "properties": {
                    "numer": {"type": "integer"},
                    "uzasadnienie": {"type": "string"},
                },
            },
        },
        "tekst": {"type": "string", "description": "Gotowy tekst postu."},
        "znakow": {
            "type": "integer",
            "description": "Dlugosc tekstu ze spacjami i znakami nowej linii.",
        },
        "pytania": {
            "type": "array",
            "description": "Pytania do instruktora, gdy czegos brakuje. Pusta lista, "
                           "gdy opis wystarczyl. Nigdy nie zmyslaj zamiast zapytac.",
            "items": {"type": "string"},
        },
        "wymaga_oka": {
            "type": "boolean",
            "description": "true, gdy cokolwiek jest na granicy i instruktor musi "
                           "obejrzec sam, zanim opublikuje.",
        },
    },
}

POLECENIE = """\
Wykonaj caly przeglad i napisz tekst postu, zgodnie z zasadami w system.

Przy kazdym otrzymanym zdjeciu podaj werdykt, takze przy odrzuconym, i zawsze
konkretny powod. Z grupy duplikatow dopusc jedno, a przy pozostalych ustaw
duplikat_do na numer tego lepszego.

Do zestawu wybierz trzy, maksymalnie cztery, w kolejnosci zgodnej z przebiegiem
zajec, ktory opisal instruktor.

Jesli opis zajec nie wystarcza, zeby napisac tekst bez zmyslania, wpisz pytania
do pola pytania i napisz tylko te czesc tekstu, ktorej jestes pewien. Nigdy nie
uzupelniaj luk domyslami.

Ustaw wymaga_oka na true, gdy cokolwiek jest na granicy: niejasne, czy dziecko
stoi na krzesle, nieczytelny papier, ktory moze byc lista z nazwiskami, cokolwiek,
czego nie jestes pewien. Lepiej zatrzymac instruktora niepotrzebnie niz wpuscic
zle zdjecie.\
"""


@dataclass
class Zdjecie:
    nazwa: str
    media_type: str
    base64: str


@dataclass
class Wynik:
    dane: dict
    koszt_usd: float
    model: str

    @property
    def dopuszczone(self) -> list[dict]:
        return [z for z in self.dane["zdjecia"] if z["decyzja"] == "dopuszczone"]

    @property
    def odrzucone(self) -> list[dict]:
        return [z for z in self.dane["zdjecia"] if z["decyzja"] == "odrzucone"]


def wczytaj_katalog(katalog: Path) -> list[Zdjecie]:
    pliki = sorted(
        s for s in katalog.iterdir()
        if s.is_file() and s.suffix.lower() in TYPY
    )
    return [
        Zdjecie(
            nazwa=s.name,
            media_type=TYPY[s.suffix.lower()],
            base64=base64.standard_b64encode(s.read_bytes()).decode(),
        )
        for s in pliki
    ]


def _koszt(model: str, u) -> float:
    we, wy = CENNIK.get(model, (0.0, 0.0))
    wejscie = (getattr(u, "input_tokens", 0) or 0) + (
        getattr(u, "cache_creation_input_tokens", 0) or 0
    )
    cache = getattr(u, "cache_read_input_tokens", 0) or 0
    return (
        wejscie / 1e6 * we
        + cache / 1e6 * we * 0.1   # odczyt z cache to okolo 10% ceny wejscia
        + (getattr(u, "output_tokens", 0) or 0) / 1e6 * wy
    )


def przeanalizuj(
    zdjecia: list[Zdjecie],
    grupa: str,
    opis: str,
    model: str = "sonnet",
    klient: "anthropic.Anthropic | None" = None,
) -> Wynik:
    """Jedno wywolanie: werdykty, zestaw, tekst postu. Zwraca Wynik."""
    if not zdjecia:
        raise ValueError("Brak zdjec do analizy.")
    if not opis.strip():
        raise ValueError("Bez opisu zajec nie da sie napisac postu.")

    model_id = MODELE.get(model, model)
    klient = klient or anthropic.Anthropic()

    bloki: list[dict] = [{
        "type": "text",
        "text": (
            f"Grupa: {grupa}\n\n"
            f"Co sie dzialo na zajeciach, wedlug instruktora:\n{opis}\n\n"
            f"Zdjecia z tych zajec, {len(zdjecia)} sztuk, ponumerowane:"
        ),
    }]
    for i, z in enumerate(zdjecia, 1):
        bloki.append({"type": "text", "text": f"Zdjecie {i}: {z.nazwa}"})
        bloki.append({
            "type": "image",
            "source": {"type": "base64", "media_type": z.media_type, "data": z.base64},
        })
    bloki.append({"type": "text", "text": POLECENIE})

    kwargs: dict = {
        "model": model_id,
        "max_tokens": 8000,
        # Zasady sa identyczne przy kazdej grupie, wiec warto je cache'owac.
        "system": [{
            "type": "text",
            "text": ZASADY.read_text(encoding="utf-8"),
            "cache_control": {"type": "ephemeral"},
        }],
        "messages": [{"role": "user", "content": bloki}],
        "output_config": {
            "format": {"type": "json_schema", "schema": SCHEMAT},
        },
    }
    # Haiku 4.5 nie przyjmuje output_config.effort; nowsze modele tak.
    if model_id != "claude-haiku-4-5":
        kwargs["output_config"]["effort"] = "medium"

    with klient.messages.stream(**kwargs) as strumien:
        odp = strumien.get_final_message()

    surowe = "".join(b.text for b in odp.content if b.type == "text")
    try:
        dane = json.loads(surowe)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model nie zwrocil poprawnego JSON: {e}\n{surowe[:400]}")

    # Model podaje znakow sam, ale liczymy u siebie: to jest twarde ograniczenie
    # aplikacji i nie moze zalezec od tego, czy model dobrze policzyl.
    dane["znakow"] = len(dane.get("tekst", ""))

    return Wynik(dane=dane, koszt_usd=_koszt(model_id, odp.usage), model=model_id)


def wypisz(w: Wynik, nazwy: list[str]) -> None:
    """Czytelny wydruk w terminalu. Interfejsy maja wlasne formatowanie."""
    def nazwa(nr: int) -> str:
        return nazwy[nr - 1] if 1 <= nr <= len(nazwy) else f"?{nr}"

    print(f"\nDOPUSZCZONE ({len(w.dopuszczone)})")
    for z in w.dopuszczone:
        print(f"  {z['numer']:>2}. {nazwa(z['numer']):<24} {z['powod']}")
        if z.get("kadrowanie"):
            print(f"      przytnij: {z['kadrowanie']}")

    print(f"\nODRZUCONE ({len(w.odrzucone)})")
    for z in w.odrzucone:
        dop = f" (duplikat {nazwa(z['duplikat_do'])})" if z.get("duplikat_do") else ""
        print(f"  {z['numer']:>2}. {nazwa(z['numer']):<24} {z['powod']}{dop}")

    print("\nZESTAW DO POSTU")
    for i, z in enumerate(w.dane["zestaw"], 1):
        print(f"  {i}. {nazwa(z['numer'])} — {z['uzasadnienie']}")

    print(f"\nTEKST ({w.dane['znakow']} znakow)")
    print("-" * 60)
    print(w.dane["tekst"])
    print("-" * 60)

    if w.dane["pytania"]:
        print("\nPYTANIA DO CIEBIE")
        for p in w.dane["pytania"]:
            print(f"  - {p}")

    if w.dane["wymaga_oka"]:
        print("\nUWAGA: cos jest na granicy, obejrzyj zdjecia sam przed publikacja.")

    print(f"\nKoszt: {w.koszt_usd:.4f} USD   Model: {w.model}")


def main() -> int:
    p = argparse.ArgumentParser(description="Przeglad i tekst postu w jednym wywolaniu.")
    p.add_argument("katalog", type=Path)
    p.add_argument("--grupa", required=True)
    p.add_argument("--opis", required=True)
    p.add_argument("--model", choices=sorted(MODELE), default="sonnet")
    p.add_argument("--json", action="store_true", help="wypisz surowy JSON")
    args = p.parse_args()

    if not args.katalog.is_dir():
        print(f"Nie ma takiego katalogu: {args.katalog}", file=sys.stderr)
        return 1

    zdjecia = wczytaj_katalog(args.katalog)
    if not zdjecia:
        print(f"Brak zdjec w {args.katalog}", file=sys.stderr)
        return 1

    w = przeanalizuj(zdjecia, args.grupa, args.opis, args.model)
    if args.json:
        print(json.dumps(w.dane, ensure_ascii=False, indent=2))
    else:
        wypisz(w, [z.nazwa for z in zdjecia])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
