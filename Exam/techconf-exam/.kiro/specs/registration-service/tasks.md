# Implementation Plan: registration-service

## Overview

Il piano implementa `registration-service` in Python con Flask, separando API, Service Layer, client HTTP e Repository. Le attività procedono dalla fondazione del servizio al comportamento applicativo, alla conformità OpenAPI e alla validazione automatizzata, senza modificare i contratti o i file protetti.

## Tasks

- [ ] 1. Creare la fondazione del servizio e i Repository intercambiabili
  - Creare `services/registration_service/` con package `app`, directory dei test, `run.py` e moduli `config.py`, `models.py`, `exceptions.py`, `repository.py` e `__init__.py`.
  - Centralizzare in `config.py` la lettura di `PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `STORAGE_BACKEND` e `DATA_DIR`, applicando i default definiti dal design.
  - Implementare la factory `create_app(...)`, l’entry point `python -m app` e `run.py`, predisponendo l’iniezione delle dipendenze e l’ascolto sulla porta configurata.
  - Definire il modello `Registration` con i soli campi `id`, `user_id`, `event_id`, `amount`, `status`, `created_at` e `updated_at`; aggiungere UUID v4, timestamp UTC ISO 8601 e serializzazione `snake_case` senza proprietà extra.
  - Definire le eccezioni applicative necessarie per validazione, risorse assenti, errori business e dipendenze indisponibili.
  - Definire l’interfaccia Repository comune con `find_by_id`, `find_all`, `save`, `delete`, `exists_confirmed` e `count_confirmed`.
  - Implementare il backend memory senza file, restituendo copie dei record per evitare mutazioni esterne.
  - Implementare il backend JSON con sola libreria standard `json`, creazione di `DATA_DIR` e scrittura atomica tramite file temporaneo e `os.replace`.
  - Implementare il backend SQLite con sola libreria standard `sqlite3`, schema e indici previsti dal design e conversione coerente dell’importo.
  - Implementare la factory del Repository per `memory`, `json` e `sqlite`, mantenendo Router e Service indipendenti dal backend.
  - Creare `requirements.txt` con sole dipendenze, a versioni esatte, `flask`, `requests`, `pytest`, `pytest-cov` e `responses`.
  _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-08, REQ-REG-09, REQ-REG-14, REQ-REG-15, REQ-REG-B04, REQ-REG-B05_

- [ ] 2. Implementare i client HTTP e il Service Layer completo
  - Creare `UserServiceClient` ed `EventServiceClient` usando base URL iniettate dalla configurazione, URL normalizzati e timeout esatto di `2.0` secondi per ogni GET.
  - Restituire i payload validi, rappresentare i `404` con un errore remoto contestualizzato e convertire timeout, connessione rifiutata, `5xx` e stati inattesi in `DependencyUnavailableError`.
  - Implementare `RegistrationService` senza dipendenze Flask e applicare nel POST l’ordine invariabile: validazione locale, verifica utente, verifica evento, evento `published`, duplicato confirmed, capienza e creazione.
  - Creare l’iscrizione solo dopo tutti i controlli, con `amount` copiato da `event.price`, stato iniziale `confirmed`, UUID v4 e timestamp correnti; non aggiornare mai lo snapshot del prezzo.
  - Implementare elenco con filtri `user_id`, `event_id` e `status` combinati in AND, `total` pre-paginazione, default e limiti di pagina, inclusa la pagina vuota.
  - Implementare GET singola, DELETE e PATCH; consentire solo `confirmed`→`cancelled` o lo stesso stato idempotente, aggiornando esclusivamente i campi ammessi e liberando capienza dopo cancellazione o eliminazione.
  - Implementare stats recuperando l’evento una volta e calcolando `confirmed` sui soli record confermati e `available=max(capacity-confirmed, 0)`.
  - Mappare il `404` remoto a `REFERENCE_NOT_FOUND` nel POST e a `NOT_FOUND` nelle stats, preservando `DEPENDENCY_UNAVAILABLE` nei due casi d’uso.
  - Rendere rintracciabili nel Service Layer tutte le regole `REQ-REG-B01`, `REQ-REG-B02`, `REQ-REG-B03`, `REQ-REG-B04`, `REQ-REG-B05`, `REQ-REG-B06`, `REQ-REG-B07`, `REQ-REG-B08`, `REQ-REG-B09`.
  _Requirements: REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-05, REQ-REG-06, REQ-REG-07, REQ-REG-08, REQ-REG-09, REQ-REG-10, REQ-REG-11, REQ-REG-12, REQ-REG-13, REQ-REG-15, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 3. Esporre l’API Flask conforme al contratto OpenAPI
  - Implementare `GET /health` con identità `registration-service` e gli endpoint POST/GET collection, GET stats, GET/PATCH/DELETE per id e PUT esplicitamente non consentito con `405`.
  - Distinguere JSON malformato da body semanticamente non valido; accettare nel POST solo `user_id` ed `event_id` e nel PATCH solo `status`.
  - Validare UUID, filtri, `page` e `page_size`, applicando i default `1` e `20`, il limite massimo `100` e passando al Service dati già normalizzati.
  - Serializzare le risposte con campi `snake_case`, impostare `Location: /api/v1/registrations/{id}` sul `201` e restituire il `204` senza body.
  - Registrare error handler uniformi nel formato `Error_Response` per `MALFORMED_JSON`, `VALIDATION_ERROR`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `REFERENCE_NOT_FOUND`, `EVENT_NOT_OPEN`, `ALREADY_REGISTERED`, `EVENT_FULL`, `INVALID_STATUS_TRANSITION` e `DEPENDENCY_UNAVAILABLE`.
  - Collegare Router, Service, Repository e client tramite dependency injection nella app factory, senza accessi diretti del Router a persistenza o dipendenze remote.
  - Usare `contracts/openapi/registration-service.yaml` come fonte di verità per path, status e schemi, senza modificarlo né aggiungere proprietà o risposte non contrattuali.
  _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-12, REQ-REG-13, REQ-REG-15, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 4. Scrivere i test unitari e di contratto
  - Testare lo stesso contratto Repository sui backend memory, JSON e SQLite con parametrizzazione e `tmp_path`: CRUD, riapertura persistente, filtri AND, duplicati confirmed, conteggio capienza, esclusione cancelled e creazione dei file prevista.
  - Testare entrambi i client con `responses` per `200`, `404`, `5xx` e stato inatteso; simulare `Timeout` e `ConnectionError` tramite patch e verificare URL e `timeout=2.0`.
  - Testare il Service Layer con repository e client mockati, verificando ordine user→event, riferimenti assenti, evento non aperto, duplicato, evento pieno, nuova iscrizione dopo cancelled e assenza di scritture prima del completamento dei controlli.
  - Verificare snapshot e immutabilità di `amount`, stato iniziale, transizione e idempotenza, divieto di riattivazione, cancellazione/eliminazione che libera un posto, filtri, paginazione e formula stats.
  - Testare Router, parsing, query, header, body vuoto del DELETE ed envelope di ogni errore tramite dependency injection.
  - Eseguire almeno una `assert_matches_contract("registration", method, path, response)` per ogni endpoint del contratto: health, POST e GET collection, stats, GET/PATCH/DELETE item e PUT `405`.
  - Configurare ed eseguire `pytest tests/unit --cov=app --cov-report=term-missing`, correggendo i difetti fino a ottenere almeno l’80% di coverage del package `app`.
  _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-03, REQ-REG-04, REQ-REG-05, REQ-REG-06, REQ-REG-07, REQ-REG-08, REQ-REG-09, REQ-REG-10, REQ-REG-11, REQ-REG-12, REQ-REG-13, REQ-REG-14, REQ-REG-15, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B04, REQ-REG-B05, REQ-REG-B06, REQ-REG-B07, REQ-REG-B08, REQ-REG-B09_

- [ ] 5. Creare i test di integrazione reali ed eseguire la validazione finale
  - Creare una fixture che individua porte libere e avvia realmente user-service, event-service e registration-service con `subprocess.Popen` e `python -m app` dalle rispettive directory.
  - Iniettare `PORT`, `USER_SERVICE_URL` ed `EVENT_SERVICE_URL`, attendere ogni servizio con polling limitato su `/health` e garantire teardown con `terminate`, `wait` e fallback `kill`; non usare mock HTTP.
  - Preparare tramite API un organizer, un utente e un evento `published`, quindi verificare una registration `201`, il relativo `Location` e `amount` uguale a `event.price`.
  - Verificare almeno utente o evento inesistente con `422 REFERENCE_NOT_FOUND` e, nello stesso flusso se compatto, evento draft con `422 EVENT_NOT_OPEN`.
  - Avviare registration-service con una dipendenza configurata su una porta chiusa e verificare `503 DEPENDENCY_UNAVAILABLE` senza attendere oltre il timeout previsto.
  - Eseguire i test di integrazione propri e il subset di collaudo relativo a registration-service; correggere eventuali regressioni senza modificare la suite del docente.
  - Verificare infine i checksum dichiarati in `CHECKSUMS.sha256` e lasciare invariati contratti, validator, collaudo e altri file protetti.
  _Requirements: REQ-REG-01, REQ-REG-02, REQ-REG-05, REQ-REG-06, REQ-REG-07, REQ-REG-10, REQ-REG-12, REQ-REG-13, REQ-REG-15, REQ-REG-B01, REQ-REG-B02, REQ-REG-B03, REQ-REG-B06, REQ-REG-B08, REQ-REG-B09_

## Notes

- Il linguaggio di implementazione è Python, come stabilito dal design.
- I cinque task sono obbligatori; non sono previsti task opzionali o property-based test.
- I test automatizzati costituiscono la verifica incrementale e finale dell’implementazione.
- `contracts/openapi/registration-service.yaml`, `contracts/validator.py`, la suite di collaudo e i file coperti da checksum restano immutati.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4", "5"] }
  ]
}
```
