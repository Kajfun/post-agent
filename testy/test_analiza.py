"""Sprawdza rdzen `analiza.py` bez wychodzenia do sieci.

Weryfikuje ksztalt zapytania, schemat strukturalnej odpowiedzi i to, co rdzen
robi z odpowiedzia modelu. Nie ocenia jakosci werdyktow.
"""

import base64
import copy
import json
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "narzedzia"))

import anthropic  # noqa: E402
from PIL import Image  # noqa: E402

import analiza  # noqa: E402

ODPOWIEDZ = {
    "zdjecia": [
        {"numer": 1, "decyzja": "dopuszczone", "powod": "Kolo z budowlami.",
         "kadrowanie": None, "duplikat_do": None},
        {"numer": 2, "decyzja": "dopuszczone", "powod": "Dzieci przy pracy.",
         "kadrowanie": "dolny pas z plecakami", "duplikat_do": None},
        {"numer": 3, "decyzja": "dopuszczone", "powod": "Zblizenie budowli.",
         "kadrowanie": None, "duplikat_do": None},
        {"numer": 4, "decyzja": "odrzucone", "powod": "To samo ujecie co 1.",
         "kadrowanie": None, "duplikat_do": 1},
    ],
    "zestaw": [
        {"numer": 1, "uzasadnienie": "Cala grupa naraz."},
        {"numer": 2, "uzasadnienie": "Praca w toku."},
        {"numer": 3, "uzasadnienie": "Efekt z bliska."},
    ],
    "tekst": "Budowali mosty.\n\nNa koniec sprawdzili, ktory uniesie wiecej.",
    "znakow": 999,  # celowo bledne: rdzen ma przeliczyc samodzielnie
    "pytania": [],
    "wymaga_oka": False,
}


class AtrapaUzycia:
    input_tokens = 50_000
    output_tokens = 900
    cache_creation_input_tokens = 3_000
    cache_read_input_tokens = 0


class AtrapaStrumienia:
    def __init__(self, tresc):
        self._tresc = tresc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text=self._tresc)],
            usage=AtrapaUzycia(),
        )


def zrob_zdjecia(katalog: Path, ile: int) -> list:
    katalog.mkdir(parents=True, exist_ok=True)
    for i in range(ile):
        Image.new("RGB", (1024, 768), (20 * i, 100, 150)).save(
            katalog / f"img{i}.jpg", "JPEG"
        )
    return analiza.wczytaj_katalog(katalog)


def main() -> int:
    baza = Path(
        "/tmp/claude-0/-home-user-post-agent/93e0ca46-9e5f-50f6-a16b-ce2b367aecf3"
        "/scratchpad/testy-analiza"
    )
    zdjecia = zrob_zdjecia(baza, 4)
    bledy = []

    def sprawdz(warunek, opis):
        print(f"  {'OK  ' if warunek else 'BLAD'}  {opis}")
        if not warunek:
            bledy.append(opis)

    for model_cli, model_id, ma_effort in [
        ("haiku", "claude-haiku-4-5", False),
        ("sonnet", "claude-sonnet-5-5", True),
        ("opus", "claude-opus-5-5", True),
    ]:
        print(f"\n--- {model_cli} ---")
        wyslane = []

        class AtrapaKlienta:
            def __init__(self):
                self.messages = types.SimpleNamespace(stream=self._stream)

            def _stream(self, **kwargs):
                wyslane.append(copy.deepcopy(kwargs))
                return AtrapaStrumienia(json.dumps(ODPOWIEDZ, ensure_ascii=False))

        w = analiza.przeanalizuj(
            zdjecia, grupa="Testowa", opis="Budowali mosty z klockow.",
            model=model_cli, klient=AtrapaKlienta(),
        )

        sprawdz(len(wyslane) == 1, f"JEDNO wywolanie, nie trzy (bylo {len(wyslane)})")
        k = wyslane[0]
        sprawdz(k["model"] == model_id, f"model to {model_id}")

        # strukturalna odpowiedz
        fmt = k["output_config"]["format"]
        sprawdz(fmt["type"] == "json_schema", "zadana strukturalna odpowiedz")
        wym = set(fmt["schema"]["required"])
        sprawdz(
            wym == {"zdjecia", "zestaw", "tekst", "znakow", "pytania", "wymaga_oka"},
            f"schemat wymaga wszystkich pol (ma {sorted(wym)})",
        )
        sprawdz(
            ("effort" in k["output_config"]) == ma_effort,
            f"effort {'ustawiony' if ma_effort else 'pominiety'}",
        )

        # zasady i cache
        sysblok = k["system"][0]
        sprawdz("USTALENIA STAŁE" in sysblok["text"], "zasady trafiaja do system")
        sprawdz(
            sysblok.get("cache_control", {}).get("type") == "ephemeral",
            "zasady oznaczone do cache",
        )
        sprawdz(
            "wszystkie dzieci mają zgodę" in sysblok["text"],
            "ustalenia instruktora sa w zasadach, ktore dostaje model",
        )

        # zdjecia
        bloki = k["messages"][0]["content"]
        obrazy = [b for b in bloki if b["type"] == "image"]
        sprawdz(len(obrazy) == 4, f"cztery zdjecia (bylo {len(obrazy)})")
        sprawdz(
            all(base64.standard_b64decode(b["source"]["data"])[:2] == b"\xff\xd8"
                for b in obrazy),
            "zdjecia to poprawny base64 JPEG",
        )
        sprawdz(
            any("Zdjecie 1: img0.jpg" in b.get("text", "") for b in bloki),
            "zdjecia sa ponumerowane",
        )
        sprawdz(
            "Budowali mosty z klockow." in bloki[0]["text"],
            "opis zajec trafia do zapytania",
        )
        # normalizujemy biale znaki: w tekscie polecenia wypada lamanie wiersza
        polecenie = " ".join(bloki[-1]["text"].lower().split())
        sprawdz(
            "nigdy nie uzupelniaj luk domyslami" in polecenie,
            "polecenie zabrania zmyslania",
        )
        sprawdz(
            "wpisz pytania do pola pytania" in polecenie,
            "polecenie kaze pytac, gdy opisu brakuje",
        )
        sprawdz(
            k["messages"][0]["role"] == "user" and len(k["messages"]) == 1,
            "jedna wiadomosc user, brak problemu z przeplataniem rol",
        )

        # co rdzen robi z odpowiedzia
        sprawdz(len(w.dopuszczone) == 3, f"trzy dopuszczone (bylo {len(w.dopuszczone)})")
        sprawdz(len(w.odrzucone) == 1, f"jedno odrzucone (bylo {len(w.odrzucone)})")
        sprawdz(
            w.odrzucone[0]["duplikat_do"] == 1,
            "odrzucony duplikat wskazuje na lepsze ujecie",
        )
        sprawdz(
            w.dane["znakow"] == len(ODPOWIEDZ["tekst"]),
            f"licznik znakow przeliczony u siebie, nie wzięty od modelu "
            f"({w.dane['znakow']} zamiast 999)",
        )

        # koszt: 53k wejscia + 0.9k wyjscia wg cennika modelu
        we, wy = analiza.CENNIK[model_id]
        oczekiwany = 53_000 / 1e6 * we + 900 / 1e6 * wy
        sprawdz(
            abs(w.koszt_usd - oczekiwany) < 1e-9,
            f"koszt policzony poprawnie ({w.koszt_usd:.4f} USD)",
        )

    # odmowy wejsciowe
    print("\n--- walidacja wejscia ---")
    for opis_bledu, wywolanie in [
        ("brak zdjec", lambda: analiza.przeanalizuj([], "G", "opis")),
        ("pusty opis", lambda: analiza.przeanalizuj(zdjecia, "G", "   ")),
    ]:
        try:
            wywolanie()
            sprawdz(False, f"{opis_bledu} ma podniesc blad")
        except ValueError:
            sprawdz(True, f"{opis_bledu} podnosi ValueError")

    print("\n--- zly JSON od modelu ---")
    class ZlyKlient:
        def __init__(self):
            self.messages = types.SimpleNamespace(
                stream=lambda **k: AtrapaStrumienia("to nie jest json")
            )
    try:
        analiza.przeanalizuj(zdjecia, "G", "opis", klient=ZlyKlient())
        sprawdz(False, "niepoprawny JSON ma podniesc blad")
    except RuntimeError as e:
        sprawdz("JSON" in str(e), "niepoprawny JSON podnosi czytelny RuntimeError")

    print("\n--- wydruk ---")
    w = analiza.przeanalizuj(
        zdjecia, "Testowa", "Budowali mosty.", klient=AtrapaKlienta()
    )
    analiza.wypisz(w, [z.nazwa for z in zdjecia])

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
