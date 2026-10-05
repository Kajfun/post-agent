"""Sprawdza ksztalt zapytania do API bez wychodzenia do sieci.

Nie weryfikuje jakosci odpowiedzi modelu, tylko to, czy skrypt wysyla
poprawnie zbudowane zadanie: zasady w system z cache, zdjecia jako bloki
base64, effort tylko tam, gdzie model go przyjmuje, i trzy kroki po kolei.
"""

import base64
import copy
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "narzedzia"))

import anthropic  # noqa: E402
from PIL import Image  # noqa: E402


class AtrapaUzycia:
    input_tokens = 1000
    output_tokens = 200
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class AtrapaOdpowiedzi:
    def __init__(self, tekst):
        self.content = [types.SimpleNamespace(type="text", text=tekst)]
        self.usage = AtrapaUzycia()


class AtrapaStrumienia:
    def __init__(self, tekst):
        self._tekst = tekst

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return AtrapaOdpowiedzi(self._tekst)


def zrob_zdjecia(katalog: Path, ile: int):
    katalog.mkdir(parents=True, exist_ok=True)
    for i in range(ile):
        img = Image.new("RGB", (800, 600), (30 * i, 90, 160))
        img.save(katalog / f"img{i}.jpg", "JPEG")


def uruchom(model_cli, katalog):
    """Odpala post.main() z atrapa klienta; zwraca liste wyslanych zadan."""
    wyslane = []

    class AtrapaKlienta:
        def __init__(self, *a, **k):
            self.messages = types.SimpleNamespace(stream=self._stream)

        def _stream(self, **kwargs):
            # kopia, bo skrypt dopisuje do tej samej listy wiadomosci
            wyslane.append(copy.deepcopy(kwargs))
            return AtrapaStrumienia(f"odpowiedz na krok {len(wyslane)}")

    import post

    with mock.patch.object(anthropic, "Anthropic", AtrapaKlienta), \
         mock.patch.object(post, "anthropic", anthropic), \
         mock.patch("builtins.input", side_effect=[""] * 10), \
         mock.patch.object(sys, "argv", [
             "post.py", str(katalog), "--grupa", "Testowa",
             "--model", model_cli, "--opis", "Budowali mosty.",
         ]):
        kod = post.main()
    return kod, wyslane


def main():
    baza = Path("/tmp/claude-0/-home-user-post-agent/93e0ca46-9e5f-50f6-a16b-ce2b367aecf3/scratchpad/testy-post")
    zrob_zdjecia(baza, 3)
    bledy = []

    def sprawdz(warunek, opis):
        print(f"  {'OK  ' if warunek else 'BLAD'}  {opis}")
        if not warunek:
            bledy.append(opis)

    for model_cli, oczekiwany_id, ma_effort in [
        ("haiku", "claude-haiku-4-5", False),
        ("sonnet", "claude-sonnet-5-5", True),
        ("opus", "claude-opus-5-5", True),
    ]:
        print(f"\n--- {model_cli} ---")
        kod, wyslane = uruchom(model_cli, baza)

        sprawdz(kod == 0, "skrypt konczy sie bez bledu")
        sprawdz(len(wyslane) == 3, f"trzy kroki, trzy zapytania (bylo {len(wyslane)})")

        pierwsze = wyslane[0]
        sprawdz(pierwsze["model"] == oczekiwany_id, f"model to {oczekiwany_id}")
        sprawdz(
            ("output_config" in pierwsze) == ma_effort,
            f"output_config {'obecny' if ma_effort else 'pominiety'}",
        )

        sysblok = pierwsze["system"][0]
        sprawdz("# Posty dla rodziców" in sysblok["text"], "zasady trafiaja do system")
        sprawdz(
            sysblok.get("cache_control", {}).get("type") == "ephemeral",
            "zasady oznaczone do cache",
        )

        bloki = pierwsze["messages"][0]["content"]
        obrazy = [b for b in bloki if b["type"] == "image"]
        sprawdz(len(obrazy) == 3, f"trzy zdjecia w zapytaniu (bylo {len(obrazy)})")
        sprawdz(
            all(b["source"]["media_type"] == "image/jpeg" for b in obrazy),
            "zdjecia maja poprawny media_type",
        )
        sprawdz(
            all(base64.standard_b64decode(b["source"]["data"])[:2] == b"\xff\xd8"
                for b in obrazy),
            "dane zdjec to poprawny base64 JPEG",
        )
        sprawdz(
            any("Zdjecie 1: img0.jpg" in b.get("text", "") for b in bloki),
            "zdjecia sa ponumerowane",
        )
        sprawdz(
            "Budowali mosty." in bloki[0]["text"],
            "opis zajec trafia do zapytania",
        )
        sprawdz(
            "jedno zdanie" in bloki[-1].get("text", ""),
            "polecenie kroku 1 jest w tej samej wiadomosci co zdjecia",
        )
        sprawdz(
            all(m["role"] == ("user" if i % 2 == 0 else "assistant")
                for i, m in enumerate(wyslane[0]["messages"])),
            "role sie przeplataja juz w pierwszym zapytaniu",
        )

        # kroki ida po kolei i historia narasta
        role3 = [m["role"] for m in wyslane[2]["messages"]]
        sprawdz(
            role3 == ["user", "assistant", "user", "assistant", "user"],
            f"historia narasta poprawnie (bylo {role3})",
        )
        sprawdz(
            all(a != b for a, b in zip(role3, role3[1:])),
            "zadne dwie wiadomosci tej samej roli nie ida pod rzad",
        )
        sprawdz(
            "licznik znakow" in wyslane[2]["messages"][-1]["content"],
            "trzeci krok prosi o tekst postu z licznikiem",
        )

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
