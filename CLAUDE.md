# Kontekst dla sesji Claude Code w tym repo

Instruktor prowadzi zajęcia z robotyki LEGO dla dzieci 6–10 lat, w kilku
grupach w kilku szkołach, raz w tygodniu. Po zajęciach wrzuca do firmowej
aplikacji post dla rodziców: tekst do 500 znaków i kilka zdjęć.

## Co jest czym

- `.claude/skills/posty/SKILL.md` — **jedyne źródło prawdy dla zasad.**
  Zmiany tylko tutaj. Poprawka instruktora **zastępuje** istniejącą regułę,
  nigdy nie dokleja się obok niej; inaczej plik zbiera sprzeczne zasady.
- `narzedzia/` — skrypty pomocnicze, opisane w README.
- `README.md` — jak tego używać co tydzień i ile to kosztuje.

## Zasady pracy w tym repo

**Nie zmyślaj niczego o zajęciach.** Nie wiesz, co było na której grupie,
dopóki instruktor nie powie. Każda grupa miała co innego, nawet przy podobnym
temacie. Jak czegoś brakuje, pytaj — to jest najważniejsza reguła w całym
projekcie, bo instruktor podpisuje tekst swoim nazwiskiem przed rodzicami.

**Mów wprost**, kiedy zdjęcie jest słabe albo tekst nie wychodzi. Instruktor
wprost o to prosił.

**Pisz po polsku**, także commity i komentarze w kodzie.

**Sekcja USTALENIA STAŁE** w SKILL.md ma pola oznaczone `DO USTALENIA`.
Dopóki któreś jest puste, obowiązuje opisane przy nim bezpieczne zachowanie
domyślne — nie wymyślaj własnego.

## Przy pracy nad postami

Przebieg ma cztery kroki i **zatrzymanie po każdym**. Nie przeskakuj do
tekstu, zanim instruktor zaakceptuje wybór zdjęć.

## Gdzie stoimy i co jest następne

Stan na teraz:

| | |
|---|---|
| Zasady, sprawdzone na trzech prawdziwych postach | działa |
| `analiza.py` — ocena zdjęć i tekst w jednym wywołaniu API | napisane, **nieuruchomione na prawdziwym API** |
| `klatki.py`, `przygotuj_zdjecia.py` | działa |
| `przeglad.py` — strona do zatwierdzania | działa, 28 asercji |
| `uruchom.py` + `start/` — przyciski bez terminala | działa, 33 asercje |
| **`publikuj.py` — wypełnianie formularza w firmowej aplikacji** | **nie istnieje** |

**Następny krok: `publikuj.py`.** Ma wypełniać formularz „Nowy post grupowy"
na `https://app.akademiarobotyka.pl/aktualnosci`, czytając `zatwierdzone.json`
z `przeglad.py`: placówka, grupa, tytuł, treść, wgranie zdjęć w kolejności,
przełącznik widoczności dla rodziców. **Zatrzymuje się przed publikacją** —
instruktor klika sam.

Żeby to napisać, trzeba najpierw uruchomić `narzedzia/rozpoznaj.py` (przycisk
`start/1. Rozpoznaj formularz`). Zrzuci on budowę formularza do katalogu
`rozpoznanie/`. Bez tego selektory są zgadywaniem ze zrzutu ekranu.

To wymaga komputera instruktora: zalogowanej przeglądarki i dostępu do tej
strony. Sesja w chmurze tego nie zrobi.

### Czego nie weryfikowano

- `analiza.py` nigdy nie wywołało prawdziwego API — brak klucza w środowisku,
  w którym powstało. Sprawdzone offline na atrapie klienta.
- Przycisków `.bat` i `.command` nie klikano na Windowsie ani na Macu.
- Progi w `przygotuj_zdjecia.py` dobrane na obrazach syntetycznych. Jest tryb
  `--kalibruj` do ustawienia ich na prawdziwych zdjęciach.
