# Zmiany

## 0.1.3

- Parser koszyka obsługuje opisy posiłków zarówno w tablicy JSON, jak i w wartościach obiektu JSON, zgodnie z iteracją koszyka w portalu. Obejmuje to tablice PHP z nieciągłymi indeksami.
- Błąd `Invalid meal descriptions` wskazuje teraz nieobsługiwany typ danych lub indeks błędnego opisu, bez treści posiłków, kluczy odpowiedzi i danych konta. Nieprawidłowy opis nadal przerywa pobieranie całego zestawu.

## 0.1.2

- Dodano konfigurację HACS, adresy dokumentacji i zgłoszeń błędów oraz instrukcję instalacji i aktualizacji przez repozytorium niestandardowe.
- Stronicowanie list dzieci i zamówień korzysta z `currentPage` i `totalResults`, tak jak interfejs portalu. Po pobraniu wszystkich wyników integracja nie odpytuje nieistniejącej kolejnej strony.
- Niespójne lub niepełne wyniki nadal przerywają pobieranie bez nadpisywania kalendarza.
- Przy błędzie formatu podczas konfiguracji i ponownego logowania dziennik HA podaje etap i szczegół walidacji, bez danych konta, tokenów i treści zamówień.

## 0.1.1

- Naprawiono błąd HTTP 500 przy otwieraniu formularza dodawania integracji i opcji. Własna funkcja walidująca interwał nie mogła być serializowana do interfejsu HA. Formularze używają teraz standardowego selektora liczbowego HA, a dodatkowa walidacja działa po przesłaniu formularza.
- Dodano testy serializacji obu formularzy i testy walidacji interwału.

## 0.1.0

- Pierwsza wersja integracji kalendarza Obiado.
