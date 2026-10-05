# post-agent

Posty dla rodziców po zajęciach z robotyki LEGO: przegląd zdjęć, wybór
zestawu, tekst do 500 znaków, osobno dla każdej grupy.

To repo jest **źródłem prawdy dla zasad**. Cotygodniową robotę robisz gdzie
indziej — w aplikacji Claude albo skryptem przez API. Zasady zostają tutaj,
bo każda twoja poprawka ma być widocznym commitem, a nie kolejną wersją pliku
zgubioną w czacie.

---

## Najpierw: pięć rzeczy do ustalenia

W `.claude/skills/posty/SKILL.md` jest sekcja **USTALENIA STAŁE** z pięcioma
polami oznaczonymi `DO USTALENIA`. Każde ma na razie bezpieczne zachowanie
domyślne, więc da się pracować bez nich — ale dopóki są puste, model będzie
co tydzień dopytywał o to samo.

| Pole | Dlaczego to ważne | Zachowanie do czasu ustalenia |
|---|---|---|
| **Zgody na wizerunek** | Największa dziura w pierwotnych zasadach. Zakazywały kartki z nazwiskami, a o twarzach dzieci milczały | Unikamy rozpoznawalnych twarzy, każda wyraźna jest zgłaszana |
| **Lista grup** | Skład grupy zmienia tekst: „zaczęliśmy od poznania się" jest fałszem w grupie, która zna się z zeszłego roku | Pytanie przy każdym poście |
| **Limit znaków** | Czy 500 to ze spacjami i czy aplikacja przyjmuje puste linie | Liczone najostrożniej, ze spacjami i znakami nowej linii |
| **Imiona dzieci** | Zasady zakazywały nazwisk na papierach, o imionach w tekście nie mówiły | Nigdy |
| **Minimum zdjęć** | Co robić, gdy po ostrej selekcji zostają dwa | Nie dobieramy z odrzuconych, pytamy |

Wypełnij je raz i przestajemy o tym gadać.

---

## Jak tego używać co tydzień

### Wariant A: aplikacja Claude (nic nie instalujesz)

Wrzuć `SKILL.md` do wiedzy Projektu w aplikacji Claude i pracuj z telefonu.

Trzy rzeczy, które **mocno** zmniejszają zużycie limitu i nic nie kosztują:

1. **Nowy czat na każdą grupę.** W jednym wątku każde poprzednie zdjęcie jest
   wysyłane od nowa przy każdej twojej wiadomości. Cztery grupy w jednym
   czacie to zdjęcia z pierwszej policzone kilkanaście razy. To prawdopodobnie
   największa pojedyncza oszczędność.
2. **Skasuj duplikaty sam** w galerii, zanim cokolwiek wyślesz. Pięć wariantów
   tego samego ujęcia widzisz szybciej niż model.
3. **Osiem zdjęć zamiast dwudziestu**, zmniejszonych.

Punkty 2 i 3 robi za ciebie skrypt niżej, jeśli masz pod ręką komputer.

**Uwaga:** limit jest wspólny dla Claude.ai, aplikacji mobilnej, desktopowej
i Claude Code. Przeniesienie postów na telefon **nie** zwalnia limitu na
kodowanie — to ta sama pula.

### Wariant B: API (całkiem poza limitem abonamentu)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 1. mechaniczna selekcja: duplikaty, rozmycie, ciemność, zmniejszenie
python3 narzedzia/przygotuj_zdjecia.py ~/zdjecia/czwartek

# 2. przegląd, wybór i tekst, z zatrzymaniem po każdym kroku
python3 narzedzia/post.py ~/zdjecia/czwartek/do-wyslania \
    --grupa "Mickiewicza czwartek" --model sonnet
```

Rozliczane od tokenów, nie z puli abonamentu. Po każdym kroku skrypt czeka:
Enter idzie dalej, wpisana uwaga wraca do modelu jako poprawka. Na końcu
pokazuje koszt przebiegu.

---

## Ile to kosztuje

Zdjęcie kosztuje `szerokość × wysokość / 750` tokenów. Pełnowymiarowe zdjęcie
z telefonu to po przeskalowaniu **ok. 2 460 tokenów** — czyli jedno zdjęcie
kosztuje tyle, co cały plik zasad. **Tekst jest darmowy w porównaniu ze
zdjęciami**, więc cała optymalizacja dotyczy zdjęć.

Przy 4 grupach × 12 zdjęć tygodniowo, po przepuszczeniu przez
`przygotuj_zdjecia.py`:

| Model | $/1M wej. | Miesięcznie |
|---|---|---|
| `--model haiku` | $1 | **~0,30 $** |
| `--model sonnet` | $2 | **~0,60 $** |
| `--model opus` | $4 | ~2,50 $ |

Sonnet to rozsądny domyślny wybór. Opus bierz, gdy chcesz ostrzejszego oka na
drobiazgi w tle: kartkę z nazwiskami, kurtkę, dziecko klęczące na krześle.

---

## Co jest w repo

```
.claude/skills/posty/SKILL.md   zasady, jedyne źródło prawdy
narzedzia/przygotuj_zdjecia.py  mechaniczna selekcja i zmniejszanie zdjęć
narzedzia/post.py               cały przebieg przez API
testy/test_post.py              weryfikacja kształtu zapytania, bez sieci
```

### `przygotuj_zdjecia.py`

Robi tylko to, czego nie trzeba płacić modelowi:

- **duplikaty** — percepcyjny hash różnicowy, z grupy prawie identycznych
  ujęć zostaje najostrzejsze
- **rozmycie** — wariancja laplasjanu
- **ciemne i prześwietlone** — średnia jasność; sprawdzane *przed* ostrością,
  bo ciemne zdjęcie ma z definicji niski kontrast i inaczej zawsze
  raportowałoby się jako rozmazane
- **zmniejszenie** do 1024 px dłuższego boku

Reszta kryteriów (dziecko na krześle, kartka z nazwiskami, bałagan) wymaga
patrzenia i zostaje dla modelu.

**Pierwszy raz skalibruj próg ostrości na swoich zdjęciach** — zależy od
aparatu i światła w sali:

```bash
python3 narzedzia/przygotuj_zdjecia.py ~/zdjecia/czwartek --kalibruj
```

Wypisze ostrość każdego zdjęcia bez odrzucania czegokolwiek. Obejrzyj je,
znajdź granicę między ostrymi a rozmazanymi i podaj ją przez
`--prog-ostrosci`. Domyślne 120 to wartość wyjściowa, nie zmierzona na twoim
sprzęcie.

Nic nie jest kasowane — wynik ląduje w podkatalogu `do-wyslania/`.

---

## Stan weryfikacji

- `przygotuj_zdjecia.py` — uruchomiony na wygenerowanym zestawie testowym
  (ostre, duplikaty, rozmazane, ciemne, prześwietlone). Rozpoznaje wszystkie
  przypadki i podaje poprawny powód odrzucenia.
- `post.py` — **nie był uruchomiony przeciwko prawdziwemu API**, bo w
  środowisku, w którym powstał, nie było klucza. Sprawdzony offline na
  atrapie klienta: 16 asercji na każdy z trzech modeli (kształt zapytania,
  zdjęcia jako base64, zasady w `system` z cache, przeplatanie ról, kolejność
  kroków). Pierwsze prawdziwe uruchomienie może wymagać drobnej poprawki.
- Progi w `przygotuj_zdjecia.py` dobrane na syntetycznych obrazach, nie na
  zdjęciach z twoich zajęć. Stąd tryb `--kalibruj`.

---

## Czego świadomie tu nie ma

**Pełnej automatyzacji.** Cała wartość tego procesu leży w czterech
zatrzymaniach, w których patrzysz i mówisz „nie, tego zdjęcia nie".
Automatyzacja, która je usuwa, usuwa powód, dla którego to powstało. Skrypty
wyżej robią przegląd i oddają ci wybór.

**Weryfikacji zgód na wizerunek.** Model tego nie rozpozna i nigdy nie
rozpozna. Ostatnie spojrzenie przed publikacją jest twoje.

---

## Kolejny krok, jeśli chcesz to mieć na telefonie

Masz skonfigurowany n8n. Naturalny kształt: bot na Telegramie przyjmuje
zdjęcia i trzy zdania opisu, n8n woła to samo API, odsyła przegląd i tekst.
Zachowuje wszystkie cztery zatrzymania — bot proponuje, ty decydujesz.
Jakieś dwie godziny roboty. W tej sesji serwer n8n nie wstał (błąd
połączenia), więc tego nie ruszałem.
