"""Sprawdza wyciaganie klatek z nagran na wygenerowanych plikach wideo.

Kluczowe zachowania: nagranie rozmazane nie daje nic, nagranie z ruchem daje
klatki z roznych momentow, a --ile jest respektowane.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "narzedzia"))

import klatki  # noqa: E402
from przygotuj_zdjecia import dhash, odleglosc  # noqa: E402

BAZA = Path(
    "/tmp/claude-0/-home-user-post-agent/93e0ca46-9e5f-50f6-a16b-ce2b367aecf3"
    "/scratchpad/testy-klatki"
)


def ffmpeg(*args) -> None:
    subprocess.run(["ffmpeg", "-v", "error", *args, "-y"], check=True,
                   capture_output=True)


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("Brak ffmpeg, pomijam test.")
        return 0

    shutil.rmtree(BAZA, ignore_errors=True)
    BAZA.mkdir(parents=True)
    bledy = []

    def sprawdz(warunek, opis):
        print(f"  {'OK  ' if warunek else 'BLAD'}  {opis}")
        if not warunek:
            bledy.append(opis)

    # nagranie z realnie zmieniajaca sie trescia
    ffmpeg("-f", "lavfi", "-i",
           "life=size=640x480:rate=15:mold=10:life_color=white:death_color=blue",
           "-t", "15", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           str(BAZA / "ruch.mp4"))
    # nagranie rozmazane od poczatku do konca
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=640x480:rate=30:duration=8",
           "-vf", "boxblur=15:3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           str(BAZA / "rozmyte.mp4"))

    print("\n--- nagranie rozmazane ---")
    wy = BAZA / "w1"
    ile = klatki.przetworz(BAZA / "rozmyte.mp4", wy, ile=3, maks_px=1024)
    sprawdz(ile == 0, f"rozmazane nagranie nie daje zadnej klatki (dalo {ile})")
    sprawdz(
        not wy.exists() or not list(wy.glob("*.jpg")),
        "nie zapisano zadnego pliku z rozmazanego nagrania",
    )

    print("\n--- nagranie z ruchem ---")
    wy = BAZA / "w2"
    ile = klatki.przetworz(BAZA / "ruch.mp4", wy, ile=3, maks_px=1024)
    sprawdz(ile == 3, f"nagranie z ruchem daje trzy klatki (dalo {ile})")

    pliki = sorted(wy.glob("*.jpg"))
    sprawdz(len(pliki) == 3, f"trzy pliki na dysku (jest {len(pliki)})")

    hashe = [dhash(p) for p in pliki]
    odleglosci = [
        odleglosc(hashe[i], hashe[j])
        for i in range(len(hashe)) for j in range(i + 1, len(hashe))
    ]
    sprawdz(
        all(d > klatki.PROG_DUPLIKATU_KLATEK for d in odleglosci),
        f"klatki sa z roznych momentow, nie duplikatami (odleglosci {odleglosci})",
    )

    from PIL import Image
    with Image.open(pliki[0]) as img:
        sprawdz(max(img.size) <= 1024, f"klatka zmniejszona do 1024 px (jest {img.size})")

    print("\n--- --ile jest respektowane ---")
    wy = BAZA / "w3"
    ile = klatki.przetworz(BAZA / "ruch.mp4", wy, ile=1, maks_px=800)
    sprawdz(ile == 1, f"--ile 1 daje jedna klatke (dalo {ile})")
    with Image.open(next(wy.glob("*.jpg"))) as img:
        sprawdz(max(img.size) <= 800, f"--maks-px 800 respektowane (jest {img.size})")

    print("\n--- dlugosc nagrania ---")
    czas = klatki.dlugosc(BAZA / "ruch.mp4")
    sprawdz(14 <= czas <= 16, f"ffprobe podaje dlugosc ~15 s (podal {czas:.1f})")
    sprawdz(
        klatki.dlugosc(BAZA / "nie-ma-takiego.mp4") == 0.0,
        "brakujacy plik daje dlugosc 0.0, bez wyjatku",
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
