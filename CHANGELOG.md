# Zmiany

## 0.1.1

- Naprawiono błąd HTTP 500 przy otwieraniu formularza dodawania integracji i opcji. Własna funkcja walidująca interwał nie mogła być serializowana do interfejsu HA. Formularze używają teraz standardowego selektora liczbowego HA, a dodatkowa walidacja działa po przesłaniu formularza.
- Dodano testy serializacji obu formularzy i testy walidacji interwału.

## 0.1.0

- Pierwsza wersja integracji kalendarza Obiado.
