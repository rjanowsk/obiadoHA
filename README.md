# Obiado dla Home Assistant

Niestandardowa integracja tworząca **kalendarz zamówionych posiłków jednego dziecka**.
Adres firmy, login, hasło, nazwę dziecka i częstotliwość pobierania podaje się w interfejsie Home Assistant.
Domyślny okres odświeżania: **6 godzin**. Dla kolejnego dziecka dodaj drugi wpis integracji.

## Instalacja

### Przez HACS (zalecane)

Wymagany jest zainstalowany i skonfigurowany [HACS](https://www.hacs.dev/docs/use/). Repozytorium dodaje się jako niestandardowe:

1. Otwórz **HACS** w Home Assistant.
2. W menu **⋮ → Repozytoria niestandardowe / Custom repositories** wpisz `https://github.com/rjanowsk/obiadoHA`.
3. Wybierz typ **Integracja / Integration** i kliknij **Dodaj / Add**.
4. Wyszukaj **Obiado**, otwórz jego stronę i wybierz **Pobierz / Download**. Jeśli HACS pyta o wersję, wybierz `main`.
5. Uruchom ponownie Home Assistant.
6. Przejdź do konfiguracji opisanej poniżej.

HACS pobiera pliki integracji do `custom_components/obiado`. Repozytorium korzysta obecnie z gałęzi `main`, bez wydań GitHub Releases.

### Ręcznie

1. Skopiuj katalog `custom_components/obiado` do `/config/custom_components/obiado` w Home Assistant.
2. Uruchom ponownie Home Assistant.
3. Przejdź do konfiguracji opisanej poniżej.

### Konfiguracja w Home Assistant

1. Otwórz **Ustawienia → Urządzenia i usługi → Dodaj integrację → Obiado**.
2. Podaj adres, np. `rpk.obiado.pl`, login i hasło do Obiado, oraz nazwisko i imię dokładnie jak na przycisku wyboru dziecka w portalu, np. `Kowalski Jan`.
3. Pozostaw 6 godzin lub podaj inny okres od 1 do 168 godzin. Ułamki godzin są obsługiwane.
4. Powtórz dla `Kowalska Anna`, jeżeli chcesz mieć kalendarze dla kilku dzieci.

Kalendarze będą dostępne w panelu **Kalendarz**. Rzeczywiste identyfikatory encji sprawdzisz w ustawieniach integracji.
Interwał możesz później zmienić przyciskiem **Konfiguruj**. Ręczne odświeżenie jest możliwe akcją `homeassistant.update_entity` dla encji kalendarza.
Zmiana firmy lub dziecka wymaga usunięcia danego wpisu integracji i dodania nowego. W razie wygaśnięcia logowania HA wyświetli formularz ponownego uwierzytelnienia.

### Aktualizacje i przejście z instalacji ręcznej

Aktualizacje pobieraj przez HACS ze strony **Obiado**, a następnie uruchom ponownie Home Assistant. Jeśli pliki były wcześniej kopiowane ręcznie, dodaj repozytorium i pobierz integrację w HACS według powyższych kroków, po czym zrestartuj HA. Istniejące wpisy integracji i kalendarze pozostają skonfigurowane; nie trzeba ponownie dodawać dzieci.

### Diagnostyka

Po aktualizacji plików integracji uruchom ponownie Home Assistant. Jeśli formularz zgłasza „Nieoczekiwany format danych Obiado”, sprawdź **Ustawienia → System → Dzienniki**. Od wersji 0.1.2 wpis `Obiado setup rejected the response` wskazuje etap (`Login/current user`, `Children list`, `Orders list` lub `Monthly basket`) i powód odrzucenia odpowiedzi. Do zgłoszenia błędu wystarczy ten wpis; nie przesyłaj haseł, tokenów ani pełnych odpowiedzi API.

Wersja 0.1.3 obsługuje również opisy posiłków zapisane jako wartości obiektu JSON. Jeśli nadal występuje `Monthly basket: Invalid meal descriptions`, prześlij cały ten wpis: wskazuje on teraz typ nieobsługiwanej wartości lub indeks pustego opisu.

Projekt używa współczesnego API wpisów konfiguracji HA (`runtime_data`, przepływ opcji i reautoryzacja). Zalecany jest aktualny stabilny Home Assistant. Testy uruchamiane na tym komputerze nie obejmują pełnego środowiska HA; patrz „Weryfikacja”.

## Zasady synchronizacji

- Jedno całodniowe wydarzenie na datę. Tytuł zawiera menu, np. `Obiad — Danie główne 2: zapiekanka z kurczakiem · Napój: sok pomarańczowy`, więc posiłki są widoczne również w kartach wyświetlających sam tytuł. Opis zawiera nazwę dziecka i wszystkie pozycje koszyka w osobnych punktach, z dietą w osobnym wierszu. Nazwy dań i dieta pojawiają się, jeżeli portal je zwróci. Zawijanie długiego tytułu zależy od użytej karty kalendarza.
- Każde **pełne i poprawne** pobranie zastępuje cały zestaw wydarzeń tego kalendarza. Zmiany zamówień pojawiają się w opisie, a usunięte zamówienia znikają. Poprawny pusty wynik czyści kalendarz.
- Błąd sieci, logowania, nieznany format lub przerwane stronicowanie nie nadpisują poprzedniego zestawu. Encja sygnalizuje niedostępność.
- Wydarzenia dla `data < dziś - 5 dni` są usuwane. Wpis z datą dokładnie `dziś - 5 dni` pozostaje. Dla 18.10.2026 pozostają daty od 13.10.2026.
- Granica dnia wynika ze strefy czasowej HA. Czyszczenie działa również lokalnie o północy, niezależnie od interwału i dostępności portalu.
- Dane są zapisywane w magazynie HA, osobno dla każdego wpisu. Usunięcie integracji usuwa także jej lokalny magazyn. Integracja nie modyfikuje innych kalendarzy.
- Lista zamówień konta służy do wykrywania miesięcy z zamówieniami, bez arbitralnego limitu przyszłych miesięcy. Następnie pobierany jest miesięczny koszyk wyłącznie skonfigurowanego dziecka.

## Dostęp i prywatność

Integracja wykonuje tylko `POST https://api.obiado.pl/api/auth/login` oraz odczyty `GET`: bieżący użytkownik, lista jego dzieci, lista zamówień i koszyk dziecka. Nie ma metod zamawiania, anulowania, płatności ani zmiany konta. Adres cateringu jest ograniczony do domeny `obiado.pl`; przekierowania API są wyłączone, a TLS jest weryfikowany.

Login i hasło przechowuje Home Assistant w swoim wpisie konfiguracji (standardowy magazyn `.storage`, bez dodatkowego szyfrowania przez tę integrację). Token jest tylko w pamięci. Zabezpiecz dostęp do konfiguracji i kopii zapasowych HA. Kod nie loguje haseł, tokenów, treści zamówień ani pełnych odpowiedzi portalu.

## Weryfikacja i ograniczenia

Na zalogowanym portalu sprawdzono wybór dziecka i widok koszyka. Protokół API ustalono z publicznego kodu aplikacji Obiado: logowanie `username/password`, token Bearer, nagłówek `X-Tenant-Slug`, lista dzieci `fullName.name`, koszyk `orders: {data: [opisy]}`.

**Nie przeprowadzono jeszcze pełnego testu integracji na działającym Home Assistant ani logowania klienta Python na rzeczywistym koncie.** Sesja przeglądarki nie jest przekazywana do integracji. Formularz HA sprawdza logowanie i pełne pobranie przed zapisaniem konfiguracji. Przed użyciem produkcyjnym zweryfikuj oba kalendarze względem koszyka.

Obiado nie udostępnia tu potwierdzonego, wersjonowanego kontraktu API. Zmiana portalu może wymagać aktualizacji klienta. Nieznana odpowiedź zatrzymuje synchronizację zamiast publikować niepełny wynik. Konto musi mieć dostęp rodzica do dziecka. Nazwa musi wskazywać dokładnie jedno dziecko.

Testy lokalne (Python 3.12+, również Windows):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\ruff check custom_components tests
.venv\Scripts\ruff format --check custom_components tests
```

Testy obejmują kontrakt klienta na symulowanych odpowiedziach, ponawianie logowania, stronicowanie, blokadę nieznanych endpointów, odległe miesiące, format koszyka i granicę retencji. Testy wymagające Home Assistant są na Windows pomijane; workflow CI uruchamia je na Linuksie z prawdziwym HA.

Dokumentacja użytego API Home Assistant: [CalendarEntity](https://developers.home-assistant.io/docs/core/entity/calendar/), [config flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/).
