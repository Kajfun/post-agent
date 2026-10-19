#!/usr/bin/env python3
"""Strona do zatwierdzania postow, otwierana lokalnie.

Czyta plik z przygotowanymi postami, pokazuje kazdy jako karte ze zdjeciami
i tekstem, pozwala poprawic tekst i zaznaczyc, ktore ida w swiat. Po klknieciu
zapisuje zatwierdzone i konczy prace. Publikacje robi `publikuj.py`.

Nie uzywa zadnych bibliotek spoza Pythona i nie wychodzi do sieci: serwer
slucha wylacznie na localhost.

Uzycie:
    python3 narzedzia/przeglad.py posty.json
    python3 narzedzia/przeglad.py posty.json --port 8900 --bez-przegladarki

Format pliku wejsciowego: lista obiektow
    [{"placowka": "...", "grupa": "...", "tytul": "...",
      "tresc": "...", "zdjecia": ["sciezka.jpg", ...]}]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

LIMIT_ZNAKOW = 500
CEL_ZNAKOW = 250

STRONA = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zatwierdzanie postów</title>
<style>
  :root {
    --tlo: #f4f4f5; --karta: #fff; --tekst: #18181b; --slaby: #71717a;
    --kreska: #e4e4e7; --akcent: #7c3aed; --ok: #15803d; --zle: #b91c1c;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --tlo: #18181b; --karta: #27272a; --tekst: #fafafa; --slaby: #a1a1aa;
      --kreska: #3f3f46; --akcent: #a78bfa; --ok: #4ade80; --zle: #f87171;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px 140px; background: var(--tlo);
    color: var(--tekst); font: 16px/1.5 system-ui, -apple-system, sans-serif; }
  .srodek { max-width: 820px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .naglowek p { margin: 0 0 24px; color: var(--slaby); font-size: 14px; }
  .karta { background: var(--karta); border: 1px solid var(--kreska);
    border-radius: 12px; padding: 18px; margin-bottom: 18px; }
  .karta.odrzucona { opacity: .45; }
  .gdzie { font-size: 13px; color: var(--slaby); margin-bottom: 2px; }
  .grupa { font-weight: 600; margin-bottom: 14px; }
  .zdjecia { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px;
    margin-bottom: 14px; }
  .zdjecia figure { margin: 0; flex: 0 0 auto; }
  .zdjecia img { height: 150px; width: auto; border-radius: 8px; display: block;
    border: 1px solid var(--kreska); cursor: zoom-in; }
  .zdjecia figcaption { font-size: 11px; color: var(--slaby); margin-top: 4px;
    text-align: center; }
  label.pole { display: block; font-size: 12px; color: var(--slaby);
    margin: 0 0 4px; text-transform: uppercase; letter-spacing: .04em; }
  input[type=text], textarea { width: 100%; padding: 10px 12px; font: inherit;
    color: inherit; background: var(--tlo); border: 1px solid var(--kreska);
    border-radius: 8px; }
  textarea { min-height: 96px; resize: vertical; overflow: hidden; }
  .stopka { display: flex; justify-content: space-between; align-items: center;
    margin-top: 10px; gap: 12px; flex-wrap: wrap; }
  .licznik { font-variant-numeric: tabular-nums; font-size: 13px; color: var(--slaby); }
  .licznik.zle { color: var(--zle); font-weight: 600; }
  .przelacznik { display: flex; align-items: center; gap: 8px; font-size: 14px;
    cursor: pointer; user-select: none; }
  .przelacznik input { width: 18px; height: 18px; accent-color: var(--akcent); }
  .pasek { position: fixed; left: 0; right: 0; bottom: 0; background: var(--karta);
    border-top: 1px solid var(--kreska); padding: 14px 16px; }
  .pasek .srodek { display: flex; justify-content: space-between;
    align-items: center; gap: 16px; flex-wrap: wrap; }
  button { font: inherit; font-weight: 600; padding: 12px 22px; border: 0;
    border-radius: 10px; background: var(--akcent); color: #fff; cursor: pointer; }
  button:disabled { opacity: .4; cursor: not-allowed; }
  dialog { border: 0; border-radius: 12px; padding: 0; background: transparent; }
  dialog img { max-width: 92vw; max-height: 88vh; border-radius: 12px; display: block; }
  dialog::backdrop { background: rgba(0,0,0,.8); }
  .gotowe { text-align: center; padding: 60px 20px; }
  @media (max-width: 520px) { body { padding: 16px 16px 150px; } }
</style></head>
<body><div class="srodek" id="apka"></div>
<div class="pasek"><div class="srodek">
  <span class="licznik" id="podsumowanie"></span>
  <button id="wyslij">Zatwierdź zaznaczone</button>
</div></div>
<dialog id="podglad"><img alt=""></dialog>
<script>
const POSTY = __DANE__;
const LIMIT = __LIMIT__, CEL = __CEL__;
const apka = document.getElementById('apka');
const stan = POSTY.map(p => ({ ...p, zatwierdzony: true }));

apka.insertAdjacentHTML('beforeend', `<div class="naglowek">
  <h1>Zatwierdzanie postów</h1>
  <p>Popraw, co chcesz. Odznacz te, które nie mają iść. Zdjęcie kliknij, żeby powiększyć.</p>
</div>`);

stan.forEach((p, i) => {
  const karta = document.createElement('div');
  karta.className = 'karta';
  karta.innerHTML = `
    <div class="gdzie">${esc(p.placowka || '')}</div>
    <div class="grupa">${esc(p.grupa || 'bez nazwy')}</div>
    <div class="zdjecia">${(p.zdjecia || []).map((z, n) =>
      `<figure><img src="/zdjecie/${i}/${n}" alt="zdjęcie ${n + 1}">
       <figcaption>${n + 1}. ${esc(nazwa(z))}</figcaption></figure>`).join('')}</div>
    <label class="pole" for="t${i}">Tytuł</label>
    <input type="text" id="t${i}" value="${esc(p.tytul || '')}">
    <label class="pole" for="c${i}" style="margin-top:12px">Treść</label>
    <textarea id="c${i}">${esc(p.tresc || '')}</textarea>
    <div class="stopka">
      <span class="licznik" id="l${i}"></span>
      <label class="przelacznik"><input type="checkbox" id="z${i}" checked> publikuj</label>
    </div>`;
  apka.appendChild(karta);

  const tytul = karta.querySelector(`#t${i}`);
  const tresc = karta.querySelector(`#c${i}`);
  const licz = karta.querySelector(`#l${i}`);
  const zatw = karta.querySelector(`#z${i}`);

  const dopasuj = (el) => {
    el.style.height = 'auto';
    el.style.height = Math.max(el.scrollHeight, 96) + 'px';
  };
  const odswiez = () => {
    dopasuj(tresc);
    p.tytul = tytul.value; p.tresc = tresc.value;
    const n = tresc.value.length;
    licz.textContent = `${n} znaków` + (n > LIMIT ? ` — ponad limit ${LIMIT}!`
      : n < CEL ? ` (cel ~${CEL})` : '');
    licz.classList.toggle('zle', n > LIMIT);
    p.zatwierdzony = zatw.checked;
    karta.classList.toggle('odrzucona', !zatw.checked);
    podsumuj();
  };
  tytul.addEventListener('input', odswiez);
  tresc.addEventListener('input', odswiez);
  zatw.addEventListener('change', odswiez);
  karta.querySelectorAll('.zdjecia img').forEach(img => {
    img.addEventListener('click', () => {
      const d = document.getElementById('podglad');
      d.querySelector('img').src = img.src; d.showModal();
    });
  });
  odswiez();
});

document.getElementById('podglad').addEventListener('click', e => e.target.closest('dialog').close());

function podsumuj() {
  const ile = stan.filter(p => p.zatwierdzony).length;
  const zadl = stan.filter(p => p.zatwierdzony && (p.tresc || '').length > LIMIT).length;
  const s = document.getElementById('podsumowanie');
  s.textContent = zadl ? `${ile} do publikacji, ${zadl} przekracza limit znaków`
    : `${ile} z ${stan.length} do publikacji`;
  s.classList.toggle('zle', zadl > 0);
  document.getElementById('wyslij').disabled = ile === 0 || zadl > 0;
}

document.getElementById('wyslij').addEventListener('click', async () => {
  const guzik = document.getElementById('wyslij');
  guzik.disabled = true; guzik.textContent = 'Zapisuję...';
  const wybrane = stan.filter(p => p.zatwierdzony)
    .map(p => ({ nr: p.nr, tytul: p.tytul, tresc: p.tresc }));
  try {
    const odp = await fetch('/zatwierdz', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(wybrane),
    });
    if (!odp.ok) throw new Error(await odp.text());
    document.body.innerHTML = `<div class="srodek gotowe">
      <h1>Zatwierdzone: ${wybrane.length}</h1>
      <p>Wróć do terminala. Możesz zamknąć tę kartę.</p></div>`;
  } catch (e) {
    guzik.disabled = false; guzik.textContent = 'Zatwierdź zaznaczone';
    alert('Nie udało się zapisać: ' + e.message);
  }
});

function esc(s) { return String(s ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function nazwa(s) { return String(s).split(/[\\\\/]/).pop(); }
</script></body></html>
"""


def zbuduj_strone(posty: list[dict]) -> bytes:
    # Przegladarka dostaje numer postu i same nazwy plikow. Pelne sciezki
    # zostaja na serwerze: nie trafiaja do zrodla strony i nie da sie ich
    # podmienic, bo przy zatwierdzaniu bierzemy je z powrotem stad, a nie
    # z tego, co odeslala przegladarka.
    bezpieczne = [
        {
            "nr": i,
            "placowka": p.get("placowka", ""),
            "grupa": p.get("grupa", ""),
            "tytul": p.get("tytul", ""),
            "tresc": p.get("tresc", ""),
            "zdjecia": [Path(z).name for z in p.get("zdjecia", [])],
        }
        for i, p in enumerate(posty)
    ]
    html = (
        STRONA
        .replace("__DANE__", json.dumps(bezpieczne, ensure_ascii=False))
        .replace("__LIMIT__", str(LIMIT_ZNAKOW))
        .replace("__CEL__", str(CEL_ZNAKOW))
    )
    return html.encode("utf-8")


class Serwer(HTTPServer):
    def __init__(self, adres, handler, posty: list[dict], wyjscie: Path):
        super().__init__(adres, handler)
        self.posty = posty
        self.wyjscie = wyjscie
        self.zatwierdzone: list[dict] | None = None
        self.koniec = threading.Event()


class Obsluga(BaseHTTPRequestHandler):
    def log_message(self, *a):  # cisza w terminalu
        pass

    def _odpowiedz(self, kod: int, tresc: bytes, typ: str):
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(tresc)))
        self.end_headers()
        self.wfile.write(tresc)

    def do_GET(self):
        sciezka = unquote(urlparse(self.path).path)
        if sciezka in ("/", "/index.html"):
            self._odpowiedz(200, zbuduj_strone(self.server.posty), "text/html; charset=utf-8")
            return
        if sciezka.startswith("/zdjecie/"):
            self._wyslij_zdjecie(sciezka)
            return
        self._odpowiedz(404, b"nie ma", "text/plain; charset=utf-8")

    def _wyslij_zdjecie(self, sciezka: str):
        # /zdjecie/<nr postu>/<nr zdjecia>; indeksy, nie sciezki z adresu,
        # zeby przegladarka nie mogla poprosic o dowolny plik z dysku.
        czesci = sciezka.strip("/").split("/")
        if len(czesci) != 3:
            self._odpowiedz(404, b"nie ma", "text/plain; charset=utf-8")
            return
        try:
            post = self.server.posty[int(czesci[1])]
            plik = Path(post["zdjecia"][int(czesci[2])])
        except (IndexError, ValueError, KeyError):
            self._odpowiedz(404, b"nie ma", "text/plain; charset=utf-8")
            return
        if not plik.is_file():
            self._odpowiedz(404, b"brak pliku", "text/plain; charset=utf-8")
            return
        typ = mimetypes.guess_type(plik.name)[0] or "application/octet-stream"
        self._odpowiedz(200, plik.read_bytes(), typ)

    def _scal(self, wpis: dict) -> dict:
        """Laczy poprawki z przegladarki z oryginalem po stronie serwera."""
        if not isinstance(wpis, dict):
            raise ValueError("kazdy wpis ma byc obiektem")
        nr = wpis["nr"]
        if not isinstance(nr, int) or not 0 <= nr < len(self.server.posty):
            raise IndexError(f"numer postu poza zakresem: {nr!r}")
        oryginal = self.server.posty[nr]
        tresc = wpis.get("tresc", oryginal.get("tresc", ""))
        if not isinstance(tresc, str) or not isinstance(wpis.get("tytul", ""), str):
            raise ValueError("tytul i tresc maja byc tekstem")
        if len(tresc) > LIMIT_ZNAKOW:
            raise ValueError(f"tresc postu {nr} ma {len(tresc)} znakow, limit to {LIMIT_ZNAKOW}")
        return {
            **oryginal,
            "tytul": wpis.get("tytul", oryginal.get("tytul", "")),
            "tresc": tresc,
        }

    def do_POST(self):
        if urlparse(self.path).path != "/zatwierdz":
            self._odpowiedz(404, b"nie ma", "text/plain; charset=utf-8")
            return
        dlugosc = int(self.headers.get("Content-Length") or 0)
        try:
            dane = json.loads(self.rfile.read(dlugosc).decode("utf-8"))
            if not isinstance(dane, list):
                raise ValueError("oczekiwano listy postow")
            wynik = [self._scal(wpis) for wpis in dane]
        except (json.JSONDecodeError, ValueError, TypeError,
                KeyError, IndexError, UnicodeDecodeError) as e:
            self._odpowiedz(400, str(e).encode(), "text/plain; charset=utf-8")
            return

        self.server.wyjscie.write_text(
            json.dumps(wynik, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.server.zatwierdzone = wynik
        self._odpowiedz(200, b'{"ok":true}', "application/json")
        self.server.koniec.set()


def main() -> int:
    p = argparse.ArgumentParser(description="Strona do zatwierdzania postow.")
    p.add_argument("plik", type=Path, help="JSON z przygotowanymi postami")
    p.add_argument("--wyjscie", type=Path, default=Path("zatwierdzone.json"))
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--bez-przegladarki", action="store_true")
    args = p.parse_args()

    if not args.plik.is_file():
        print(f"Nie ma takiego pliku: {args.plik}", file=sys.stderr)
        return 1
    try:
        posty = json.loads(args.plik.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Niepoprawny JSON w {args.plik}: {e}", file=sys.stderr)
        return 1
    if not isinstance(posty, list) or not posty:
        print(f"{args.plik} ma zawierac niepusta liste postow.", file=sys.stderr)
        return 1

    for i, post in enumerate(posty, 1):
        brakuje = [p.get("zdjecia", []) for p in [post]][0]
        for z in brakuje:
            if not Path(z).is_file():
                print(f"Uwaga: post {i} wskazuje na brakujace zdjecie: {z}")

    serwer = Serwer(("127.0.0.1", args.port), Obsluga, posty, args.wyjscie)
    adres = f"http://127.0.0.1:{args.port}/"
    print(f"Strona do zatwierdzania: {adres}")
    print(f"Postow do przejrzenia: {len(posty)}")
    print("Zatwierdz w przegladarce albo przerwij Ctrl+C.\n")

    watek = threading.Thread(target=serwer.serve_forever, daemon=True)
    watek.start()
    if not args.bez_przegladarki:
        webbrowser.open(adres)

    try:
        serwer.koniec.wait()
    except KeyboardInterrupt:
        print("\nPrzerwane, nic nie zapisano.")
        serwer.shutdown()
        return 1

    serwer.shutdown()
    ile = len(serwer.zatwierdzone or [])
    print(f"Zatwierdzone: {ile}, zapisane w {args.wyjscie}")
    print(f"Teraz: python3 narzedzia/publikuj.py {args.wyjscie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
