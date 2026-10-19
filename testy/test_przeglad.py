"""Sprawdza strone do zatwierdzania: serwer, obrazki, zapis i walidacje."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "narzedzia"))
import przeglad  # noqa: E402

BAZA = Path(
    "/tmp/claude-0/-home-user-post-agent/93e0ca46-9e5f-50f6-a16b-ce2b367aecf3"
    "/scratchpad/testy-przeglad"
)
PORT = 8791


def pobierz(sciezka, dane=None):
    url = f"http://127.0.0.1:{PORT}{sciezka}"
    if dane is None:
        with urllib.request.urlopen(url, timeout=5) as o:
            return o.status, o.read(), o.headers.get("Content-Type", "")
    req = urllib.request.Request(
        url, data=json.dumps(dane).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as o:
        return o.status, o.read(), o.headers.get("Content-Type", "")


def main() -> int:
    from PIL import Image
    BAZA.mkdir(parents=True, exist_ok=True)
    for n in range(2):
        Image.new("RGB", (400, 300), (40 * n, 120, 180)).save(BAZA / f"z{n}.jpg", "JPEG")

    posty = [{
        "placowka": "Wola Rzędzińska", "grupa": "Bursztynowa 1b i 1c",
        "tytul": "Pierwsze zajęcia", "tresc": "Każdy zbudował literę.",
        "zdjecia": [str(BAZA / "z0.jpg"), str(BAZA / "z1.jpg")],
    }, {
        "placowka": "SP17", "grupa": "Szmaragdowa",
        "tytul": "Nasze wakacje", "tresc": "Budowaliśmy wakacje.",
        "zdjecia": [str(BAZA / "z0.jpg")],
    }]
    wyjscie = BAZA / "zatwierdzone.json"
    wyjscie.unlink(missing_ok=True)

    bledy = []

    def sprawdz(w, opis):
        print(f"  {'OK  ' if w else 'BLAD'}  {opis}")
        if not w:
            bledy.append(opis)

    serwer = przeglad.Serwer(("127.0.0.1", PORT), przeglad.Obsluga, posty, wyjscie)
    threading.Thread(target=serwer.serve_forever, daemon=True).start()
    time.sleep(0.3)

    try:
        print("\n--- strona ---")
        kod, tresc, typ = pobierz("/")
        html = tresc.decode("utf-8")
        sprawdz(kod == 200, "strona glowna odpowiada 200")
        sprawdz("charset=utf-8" in typ, "strona deklaruje utf-8")
        sprawdz("Bursztynowa 1b i 1c" in html, "nazwa grupy jest na stronie")
        sprawdz("Wola Rzędzińska" in html, "polskie znaki przetrwaly")
        sprawdz("__DANE__" not in html and "__LIMIT__" not in html,
                "wszystkie znaczniki podmienione")
        sprawdz(str(przeglad.LIMIT_ZNAKOW) in html, "limit znakow trafia do strony")
        sprawdz('/zdjecie/${i}/${n}' in html, "zdjecia adresowane po numerach")
        sprawdz('"nr": 0' in html or '"nr":0' in html, "posty maja numery")
        sprawdz('"z0.jpg"' in html, "do przegladarki ida same nazwy plikow")
        sprawdz(str(BAZA) not in html, "sciezki z dysku nie wyciekaja do HTML")

        print("\n--- zdjecia ---")
        kod, dane, typ = pobierz("/zdjecie/0/1")
        sprawdz(kod == 200 and dane[:2] == b"\xff\xd8", "zdjecie serwowane jako JPEG")
        sprawdz(typ == "image/jpeg", f"poprawny Content-Type (jest {typ})")

        for zly, opis in [
            ("/zdjecie/9/0", "nieistniejacy post"),
            ("/zdjecie/0/9", "nieistniejace zdjecie"),
            ("/zdjecie/a/b", "nieliczbowy indeks"),
            ("/zdjecie/0/0/../../../etc/passwd", "proba wyjscia poza katalog"),
            ("/nie-ma-takiej", "nieznana sciezka"),
        ]:
            try:
                pobierz(zly)
                sprawdz(False, f"{opis} ma dac 404")
            except urllib.error.HTTPError as e:
                sprawdz(e.code == 404, f"{opis} daje 404")

        print("\n--- zapis zatwierdzonych ---")
        try:
            pobierz("/zatwierdz", {"nie": "lista"})
            sprawdz(False, "zly ksztalt danych ma dac 400")
        except urllib.error.HTTPError as e:
            sprawdz(e.code == 400, "zly ksztalt danych daje 400")
        sprawdz(not wyjscie.exists(), "bledne zadanie nic nie zapisalo")

        # Probujemy przy okazji podstawic wlasna sciezke do pliku:
        # serwer ma ja zignorowac i wziac swoja.
        wybrane = [{"nr": 0, "tytul": "Pierwsze zajęcia",
                    "tresc": "Poprawiona treść.", "zdjecia": ["/etc/passwd"]}]
        kod, odp, _ = pobierz("/zatwierdz", wybrane)
        sprawdz(kod == 200, "zatwierdzenie odpowiada 200")
        sprawdz(serwer.koniec.wait(timeout=2), "serwer dostaje sygnal konca")

        zapisane = json.loads(wyjscie.read_text(encoding="utf-8"))
        sprawdz(len(zapisane) == 1, f"zapisany jeden post (jest {len(zapisane)})")
        sprawdz(zapisane[0]["tresc"] == "Poprawiona treść.",
                "poprawiona tresc trafia do pliku, nie oryginalna")
        sprawdz(zapisane[0]["grupa"] == "Bursztynowa 1b i 1c", "grupa zachowana")
        sprawdz(zapisane[0]["zdjecia"] == posty[0]["zdjecia"],
                "sciezki do zdjec pochodza z serwera, nie z przegladarki")
        sprawdz(zapisane[0]["placowka"] == "Wola Rzędzińska",
                "pola nieedytowalne zachowane z oryginalu")

        print("\n--- walidacja przy zatwierdzaniu ---")
        for zle, opis in [
            ([{"nr": 99, "tresc": "x"}], "numer postu poza zakresem"),
            ([{"tresc": "x"}], "brak numeru postu"),
            ([{"nr": 0, "tresc": "z" * (przeglad.LIMIT_ZNAKOW + 1)}],
             "tresc ponad limit znakow"),
            (["nie obiekt"], "wpis niebedacy obiektem"),
        ]:
            try:
                pobierz("/zatwierdz", zle)
                sprawdz(False, f"{opis} ma dac 400")
            except urllib.error.HTTPError as e:
                sprawdz(e.code == 400, f"{opis} daje 400")
    finally:
        serwer.shutdown()
        serwer.server_close()

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
