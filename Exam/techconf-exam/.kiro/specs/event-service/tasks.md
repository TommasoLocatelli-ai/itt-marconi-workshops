# Implementation Plan: event-service

## Overview

Il piano implementa `event-service` in Python e Flask seguendo l'architettura Router → Service → Repository, con `UserServiceClient` dedicato e dependency injection. Le attività sono ordinate per produrre incrementi integrati e verificabili: setup, dominio, dipendenze esterne, persistenza, logica applicativa, API HTTP, test automatici e validazione finale. Il contratto `contracts/openapi/event-service.yaml`, il validator e la suite di collaudo restano invariati.

## Tasks

### 1. Setup del servizio

- [ ] 1.1 Creare la struttura del package `services/event_service`
  - Creare `app/`, `tests/unit/` e `tests/integration/`, aggiungendo gli `__init__.py` necessari ai package di test senza introdurre codice applicativo non ancora collegato.
  - _Requirements: REQ-EVT-01.8, REQ-EVT-16.4_

- [ ] 1.2 Implementare il componente unico di configurazione
  - Creare `app/config.py` e leggere esclusivamente qui `PORT` con default `5002`, `USER_SERVICE_URL` con default `http://localhost:5001`, `STORAGE_BACKEND` con default `memory` e `DATA_DIR` con default `./data`.
  - _Requirements: REQ-EVT-01.1, REQ-EVT-01.2, REQ-EVT-01.3, REQ-EVT-01.4, REQ-EVT-01.5, REQ-EVT-01.6, REQ-EVT-01.8_

- [ ] 1.3 Definire le dipendenze del servizio
  - Creare `requirements.txt` con pin esatti per il solo stack previsto: `flask` e `requests` a runtime; `pytest`, `pytest-cov` e `responses` per i test. Non aggiungere altre dipendenze runtime.
  - _Requirements: REQ-EVT-01.8, REQ-EVT-14.1, REQ-EVT-16.2, REQ-EVT-16.3_

- [ ] 1.4 Predisporre la factory Flask con dependency injection
  - Creare `app/__init__.py` con `create_app(repo=None, user_client=None)`, mantenendo espliciti i punti di iniezione e rinviando alla fase Router la registrazione definitiva di blueprint ed error handler.
  - _Requirements: REQ-EVT-01.8, REQ-EVT-16.4, REQ-EVT-16.5, REQ-EVT-16.6_

- [ ] 1.5 Implementare gli entry point del servizio
  - Creare `app/__main__.py` e `run.py` affinché `python -m app` e `python run.py` avviino la stessa factory su `0.0.0.0` usando esclusivamente `PORT` da `app.config`.
  - _Requirements: REQ-EVT-01.1, REQ-EVT-01.2_

- [ ] 1.6 Verificare automaticamente la configurazione esistente di `services.yaml`
  - Creare `tests/unit/test_manifest.py` con una verifica statica che la voce `event` esistente usi `cwd: services/event_service`, `command: python -m app` e `health_path: /health`; il test deve fallire in caso di divergenza e non deve modificare o sovrascrivere `services.yaml`.
  - _Requirements: REQ-EVT-01.1, REQ-EVT-01.2, REQ-EVT-02.1_

### 2. Modelli ed eccezioni

- [ ] 2.1 Implementare il modello `Event` e le costanti di dominio
  - Creare `app/models.py` con `Event` dataclass, `EVENT_STATUSES`, `DEFAULT_STATUS`, `ALLOWED_TRANSITIONS`, `utc_now_iso()` e `to_dict()` conforme allo schema OpenAPI; includere sempre `description`, anche quando vale `null`, e serializzare timestamp UTC e `price` come JSON number.
  - _Requirements: REQ-EVT-03.3, REQ-EVT-03.12, REQ-EVT-03.15, REQ-EVT-06.3, REQ-EVT-13.1, REQ-EVT-13.2, REQ-EVT-13.3, REQ-EVT-17.2, REQ-EVT-17.3, REQ-EVT-17.4, REQ-EVT-B04_

- [ ] 2.2 Implementare la gerarchia di eccezioni applicative
  - Creare `app/exceptions.py` con `ValidationError`, `NotFoundError`, `ReferenceNotFoundError`, `InvalidOrganizerError`, `InvalidStatusTransitionError` e `DependencyUnavailableError`, conservando i dati necessari alla successiva mappatura HTTP.
  - _Requirements: REQ-EVT-04.6, REQ-EVT-06.2, REQ-EVT-10.5, REQ-EVT-11.2, REQ-EVT-13.4, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-17.5, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B04, REQ-EVT-B05_

### 3. Client HTTP verso user-service

- [ ] 3.1 Implementare `UserServiceClient.get_user`
  - Creare `app/user_client.py` con `UserServiceClient(base_url, timeout=2.0)` e la GET `{base_url}/api/v1/users/{id}`; restituire il dizionario su 200, sollevare `ReferenceNotFoundError` su 404 e `DependencyUnavailableError` su 5xx, timeout, errore di connessione o stato inatteso. Costruire URL e timeout solo dai valori iniettati.
  - _Requirements: REQ-EVT-10.1, REQ-EVT-10.5, REQ-EVT-14.1, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-B01, REQ-EVT-B05_

- [ ] 3.2 Implementare `UserServiceClient.validate_organizer`
  - Aggiungere la validazione del campo `role`: accettare esclusivamente `organizer` e sollevare `InvalidOrganizerError` per ruoli diversi o assenti, riusando `get_user` per esistenza e resilienza.
  - _Requirements: REQ-EVT-10.6, REQ-EVT-11.1, REQ-EVT-11.2, REQ-EVT-B01, REQ-EVT-B02_

### 4. Repository Pattern

- [ ] 4.1 Definire il contratto `EventRepository`
  - Creare in `app/repository.py` l'interfaccia comune `find_by_id`, `find_all`, `save` e `delete`, con valori di ritorno uniformi e senza dipendenze da Flask o dalla logica di business.
  - _Requirements: REQ-EVT-16.4, REQ-EVT-16.5, REQ-EVT-16.6_

- [ ] 4.2 Implementare `MemoryEventRepository`
  - Aggiungere il backend in-memory per CRUD e lettura della collezione, senza creare file e senza esporre lo store interno ai chiamanti.
  - _Requirements: REQ-EVT-16.1, REQ-EVT-16.4, REQ-EVT-16.5_

- [ ] 4.3 Implementare `JsonEventRepository`
  - Aggiungere il backend JSON standard library su `{DATA_DIR}/events.json`, creare la directory se assente, usare il formato `{"events": [...]}` e persistere con scrittura atomica su file temporaneo seguita da `os.replace`.
  - _Requirements: REQ-EVT-16.2, REQ-EVT-16.4, REQ-EVT-16.5, REQ-EVT-16.7_

- [ ] 4.4 Implementare `SqliteEventRepository`
  - Aggiungere il backend con `sqlite3`, creare `{DATA_DIR}/events.db` e la tabella `events` definita dal design, usare query parametrizzate e memorizzare `price` deterministicamente restituendolo come JSON number non negativo con due decimali.
  - _Requirements: REQ-EVT-16.3, REQ-EVT-16.4, REQ-EVT-16.5, REQ-EVT-16.7, REQ-EVT-17.4_

- [ ] 4.5 Implementare la factory `get_repository`
  - Selezionare `MemoryEventRepository`, `JsonEventRepository` o `SqliteEventRepository` usando esclusivamente `STORAGE_BACKEND` e `DATA_DIR` da `app.config`; applicare il fallback a memory per valori vuoti o sconosciuti.
  - _Requirements: REQ-EVT-01.5, REQ-EVT-01.6, REQ-EVT-01.7, REQ-EVT-01.8, REQ-EVT-16.4_

### 5. Service Layer

- [ ] 5.1 Implementare `EventService` e la validazione comune
  - Creare `app/service.py` con `EventService(repo, user_client)` e helper condivisi per campi obbligatori, sconosciuti e read-only, tipi e limiti, UUID, date reali `YYYY-MM-DD`, capacità, stato e precisione massima di due decimali per `price`; mantenere tutte le regole di business fuori da Router e Repository.
  - _Requirements: REQ-EVT-03.1, REQ-EVT-03.2, REQ-EVT-03.4, REQ-EVT-03.5, REQ-EVT-03.6, REQ-EVT-03.7, REQ-EVT-03.8, REQ-EVT-03.9, REQ-EVT-03.10, REQ-EVT-03.11, REQ-EVT-03.12, REQ-EVT-03.13, REQ-EVT-03.14, REQ-EVT-17.8_

- [ ] 5.2 Implementare `EventService.create_event`
  - Validare prima i dati locali e la coerenza `end_date >= start_date`, chiamare sempre `validate_organizer`, applicare i default `description=null` e `status=draft`, generare UUID v4 e timestamp UTC, quindi salvare la risorsa completa tramite repository.
  - _Requirements: REQ-EVT-03.3, REQ-EVT-03.15, REQ-EVT-04.1, REQ-EVT-04.2, REQ-EVT-04.4, REQ-EVT-10.2, REQ-EVT-12.1, REQ-EVT-12.2, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B05_

- [ ] 5.3 Implementare `EventService.list_events`
  - Applicare `status` e città esatta case-insensitive in AND logico, calcolare `total` dopo i filtri e prima della paginazione, quindi restituire il segmento richiesto con `items`, `page`, `page_size` e `total`.
  - _Requirements: REQ-EVT-05.1, REQ-EVT-05.2, REQ-EVT-05.3, REQ-EVT-05.8, REQ-EVT-05.9, REQ-EVT-15.1, REQ-EVT-15.2, REQ-EVT-15.3, REQ-EVT-15.4, REQ-EVT-15.5, REQ-EVT-B06_

- [ ] 5.4 Implementare `EventService.get_event`
  - Recuperare la risorsa tramite repository, restituire tutti i campi previsti oppure sollevare `NotFoundError` se l'identificativo non esiste.
  - _Requirements: REQ-EVT-06.1, REQ-EVT-06.2, REQ-EVT-06.3, REQ-EVT-17.9_

- [ ] 5.5 Implementare `EventService.replace_event`
  - Richiedere tutti i campi di `EventCreate`, validare sempre l'organizzatore, applicare coerenza delle date e transizioni di stato, impostare `description=null` se omessa e conservare lo stato se omesso; preservare `id` e `created_at`, aggiornare `updated_at` e salvare tramite repository.
  - _Requirements: REQ-EVT-07.1, REQ-EVT-07.2, REQ-EVT-07.3, REQ-EVT-07.4, REQ-EVT-07.5, REQ-EVT-07.6, REQ-EVT-07.7, REQ-EVT-10.3, REQ-EVT-12.1, REQ-EVT-12.2, REQ-EVT-13.1, REQ-EVT-13.2, REQ-EVT-13.3, REQ-EVT-13.4, REQ-EVT-13.5, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05_

- [ ] 5.6 Implementare `EventService.update_event`
  - Validare e unire solo i campi PATCH presenti, chiamare user-service esclusivamente quando `organizer_id` è presente e diverso, verificare le date risultanti e la transizione di stato, preservare i campi assenti, `id` e `created_at`, quindi aggiornare `updated_at`.
  - _Requirements: REQ-EVT-08.1, REQ-EVT-08.2, REQ-EVT-08.3, REQ-EVT-08.4, REQ-EVT-08.5, REQ-EVT-08.6, REQ-EVT-08.7, REQ-EVT-08.8, REQ-EVT-10.4, REQ-EVT-12.3, REQ-EVT-13.1, REQ-EVT-13.2, REQ-EVT-13.3, REQ-EVT-13.4, REQ-EVT-13.5, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05_

- [ ] 5.7 Implementare `EventService.delete_event`
  - Eliminare tramite repository e sollevare `NotFoundError` quando la risorsa non esiste, senza lasciare accessi diretti allo storage nel Router.
  - _Requirements: REQ-EVT-09.1, REQ-EVT-09.2, REQ-EVT-16.5, REQ-EVT-16.6_

### 6. Router Flask e wiring applicativo

- [ ] 6.1 Creare il Blueprint e l'endpoint health
  - Creare `app/routes.py`, definire il Blueprint e implementare `GET /health` con stato 200 e corpo esatto `{"status":"ok","service":"event-service"}`.
  - _Requirements: REQ-EVT-02.1, REQ-EVT-02.2, REQ-EVT-17.1, REQ-EVT-17.6, REQ-EVT-17.7_

- [ ] 6.2 Implementare `POST /api/v1/events`
  - Eseguire parsing JSON non silenzioso, delegare a `EventService.create_event` e restituire 201 con la risorsa e `Location: /api/v1/events/{id}`; lasciare la mappatura di JSON malformato ed eccezioni agli handler applicativi.
  - _Requirements: REQ-EVT-04.1, REQ-EVT-04.3, REQ-EVT-04.5, REQ-EVT-04.6, REQ-EVT-17.1, REQ-EVT-17.7_

- [ ] 6.3 Implementare `GET /api/v1/events`
  - Validare `page`, `page_size`, `status` e `city`, applicare i default 1 e 20, rifiutare i valori fuori contratto con `ValidationError` e delegare filtri e paginazione al Service Layer.
  - _Requirements: REQ-EVT-05.1, REQ-EVT-05.2, REQ-EVT-05.3, REQ-EVT-05.4, REQ-EVT-05.5, REQ-EVT-05.6, REQ-EVT-05.7, REQ-EVT-05.8, REQ-EVT-05.9, REQ-EVT-B06_

- [ ] 6.4 Implementare `GET /api/v1/events/{id}`
  - Delegare il recupero a `EventService.get_event` e restituire 200 con la risorsa completa, lasciando a `NotFoundError` la produzione del 404 uniforme.
  - _Requirements: REQ-EVT-06.1, REQ-EVT-06.2, REQ-EVT-06.3, REQ-EVT-17.9_

- [ ] 6.5 Implementare `PUT /api/v1/events/{id}`
  - Eseguire parsing JSON non silenzioso, delegare la sostituzione completa al Service Layer e restituire 200, preservando le distinte mappature 400, 404, 422 e 503.
  - _Requirements: REQ-EVT-07.1, REQ-EVT-07.7, REQ-EVT-07.8, REQ-EVT-07.9, REQ-EVT-07.10, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05_

- [ ] 6.6 Implementare `PATCH /api/v1/events/{id}`
  - Eseguire parsing JSON non silenzioso, delegare l'aggiornamento parziale al Service Layer e restituire 200, preservando le distinte mappature 400, 404, 422 e 503.
  - _Requirements: REQ-EVT-08.1, REQ-EVT-08.8, REQ-EVT-08.9, REQ-EVT-08.10, REQ-EVT-08.11, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05_

- [ ] 6.7 Implementare `DELETE /api/v1/events/{id}`
  - Delegare l'eliminazione al Service Layer e restituire 204 senza body, oppure propagare `NotFoundError` per il 404 standard.
  - _Requirements: REQ-EVT-09.1, REQ-EVT-09.2_

- [ ] 6.8 Completare factory, wiring ed error handler
  - Aggiornare `app/__init__.py` per creare repository e `UserServiceClient` dai soli valori di configurazione quando non iniettati, costruire `EventService`, registrare il Blueprint e mappare JSON malformato ed eccezioni nei codici `MALFORMED_JSON`, `VALIDATION_ERROR`, `NOT_FOUND`, `REFERENCE_NOT_FOUND`, `INVALID_ORGANIZER`, `INVALID_STATUS_TRANSITION` e `DEPENDENCY_UNAVAILABLE`, sempre nel formato Error standard con `details` oggetto.
  - _Requirements: REQ-EVT-01.3, REQ-EVT-01.4, REQ-EVT-04.5, REQ-EVT-07.8, REQ-EVT-08.9, REQ-EVT-10.5, REQ-EVT-11.2, REQ-EVT-13.4, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-17.1, REQ-EVT-17.5, REQ-EVT-17.6, REQ-EVT-17.7, REQ-EVT-17.8, REQ-EVT-17.9, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B04, REQ-EVT-B05_

### 7. Fixture e configurazione dei test

- [ ] 7.1 Implementare le fixture condivise dei test
  - Creare `tests/conftest.py` con configurazione `sys.path`, factory app/client, payload Event validi, mock di `user_client` e repository parametrizzati `memory`, `json` e `sqlite` isolati tramite `tmp_path`.
  - _Requirements: REQ-EVT-01.8, REQ-EVT-10.1, REQ-EVT-16.1, REQ-EVT-16.2, REQ-EVT-16.3, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

- [ ] 7.2 Configurare pytest
  - Creare `pytest.ini` con `testpaths`, discovery coerente per unit e integration test e marker `req` registrato per associare i test agli ID `REQ-EVT-*` senza warning.
  - _Requirements: REQ-EVT-17.7, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05, REQ-EVT-B06_

### 8. Test unitari dei repository

- [ ] 8.1 Testare CRUD, filtri ed equivalenza dei tre backend
  - Creare `tests/unit/test_repository.py` con test parametrizzati su memory, JSON e SQLite per `save`, `find_by_id`, `find_all`, `delete`, persistenza su disco, directory auto-creata, filtri `status`/città, equivalenza osservabile, `description=null` e `price` restituito come number.
  - _Requirements: REQ-EVT-15.1, REQ-EVT-15.2, REQ-EVT-15.3, REQ-EVT-16.1, REQ-EVT-16.2, REQ-EVT-16.3, REQ-EVT-16.4, REQ-EVT-16.5, REQ-EVT-16.7, REQ-EVT-17.4, REQ-EVT-B06_

### 9. Test unitari del client HTTP

- [ ] 9.1 Testare tutte le risposte e gli errori di `UserServiceClient`
  - Creare `tests/unit/test_user_client.py` usando `responses` e patch mirate di `requests.get`: verificare 200, 404, ruolo errato, 5xx, stato inatteso, timeout e `ConnectionError`; asserire esplicitamente URL derivato dal `base_url` iniettato e timeout `2.0` passato alla chiamata.
  - _Requirements: REQ-EVT-10.1, REQ-EVT-10.5, REQ-EVT-10.6, REQ-EVT-11.1, REQ-EVT-11.2, REQ-EVT-14.1, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

### 10. Test unitari del Service Layer

- [ ] 10.1 Testare validazione dei campi e creazione
  - Creare `tests/unit/test_service_validation.py` con casi parametrizzati per obbligatorietà, tipi, limiti, UUID, date, precisione/prezzo, campi sconosciuti/read-only, default, UUID v4, timestamp e salvataggio della creazione valida.
  - _Requirements: REQ-EVT-03.1, REQ-EVT-03.2, REQ-EVT-03.3, REQ-EVT-03.4, REQ-EVT-03.5, REQ-EVT-03.6, REQ-EVT-03.7, REQ-EVT-03.8, REQ-EVT-03.9, REQ-EVT-03.10, REQ-EVT-03.11, REQ-EVT-03.12, REQ-EVT-03.13, REQ-EVT-03.14, REQ-EVT-03.15, REQ-EVT-04.1, REQ-EVT-04.2_

- [ ] 10.2 Testare esistenza, ruolo e indisponibilità dell'organizzatore
  - Creare `tests/unit/test_service_organizer.py` con mock del client per 404 logico, ruolo errato e indisponibilità; verificare propagazione delle eccezioni corrette e chiamata obbligatoria su create/PUT ma solo su cambio effettivo di `organizer_id` nel PATCH.
  - _Requirements: REQ-EVT-07.6, REQ-EVT-08.5, REQ-EVT-08.6, REQ-EVT-08.7, REQ-EVT-10.2, REQ-EVT-10.3, REQ-EVT-10.4, REQ-EVT-10.5, REQ-EVT-11.1, REQ-EVT-11.2, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

- [ ] 10.3 Testare coerenza date e transizioni di stato
  - Creare `tests/unit/test_service_lifecycle.py` con casi parametrizzati per date uguali, ordinate e invertite, merge PATCH delle date, tutte le transizioni valide, tutte quelle invalide e richieste idempotenti.
  - _Requirements: REQ-EVT-12.1, REQ-EVT-12.2, REQ-EVT-12.3, REQ-EVT-13.1, REQ-EVT-13.2, REQ-EVT-13.3, REQ-EVT-13.4, REQ-EVT-13.5, REQ-EVT-B03, REQ-EVT-B04_

- [ ] 10.4 Testare filtri, paginazione e total
  - Creare `tests/unit/test_service_listing.py` con dataset misti e test parametrizzati per filtro status, città esatta case-insensitive, AND, nessun risultato, pagina vuota e `total` pre-paginazione.
  - _Requirements: REQ-EVT-05.1, REQ-EVT-05.8, REQ-EVT-05.9, REQ-EVT-15.1, REQ-EVT-15.2, REQ-EVT-15.3, REQ-EVT-15.4, REQ-EVT-15.5, REQ-EVT-B06_

- [ ] 10.5 Testare le semantiche CRUD complete del Service Layer
  - Creare `tests/unit/test_service_crud.py` per create/GET/PUT/PATCH/DELETE, 404, preservazione di `id`/`created_at`, aggiornamento di `updated_at`, default PUT e preservazione dei campi PATCH assenti.
  - _Requirements: REQ-EVT-04.1, REQ-EVT-06.1, REQ-EVT-06.2, REQ-EVT-07.1, REQ-EVT-07.2, REQ-EVT-07.3, REQ-EVT-07.4, REQ-EVT-07.5, REQ-EVT-07.7, REQ-EVT-08.1, REQ-EVT-08.2, REQ-EVT-08.3, REQ-EVT-08.4, REQ-EVT-08.8, REQ-EVT-09.1, REQ-EVT-09.2_

### 11. Test Router e conformità al contratto

- [ ] 11.1 Testare endpoint, errori e contratto OpenAPI
  - Creare `tests/unit/test_routes.py` con casi positivi e principali errori per `/health`, POST, GET lista, GET per id, PUT, PATCH e DELETE; includere almeno una chiamata `assert_matches_contract("event", method, path, response)` per ciascuno dei sette endpoint e verificare 422 business e 503 dependency per POST/PUT/PATCH. Importare il validator esistente senza modificare `contracts/validator.py` o il contratto.
  - _Requirements: REQ-EVT-02.1, REQ-EVT-02.2, REQ-EVT-04.1, REQ-EVT-04.3, REQ-EVT-04.5, REQ-EVT-04.6, REQ-EVT-05.1, REQ-EVT-05.4, REQ-EVT-05.5, REQ-EVT-05.6, REQ-EVT-05.7, REQ-EVT-06.1, REQ-EVT-06.2, REQ-EVT-07.1, REQ-EVT-07.7, REQ-EVT-07.8, REQ-EVT-07.9, REQ-EVT-07.10, REQ-EVT-08.1, REQ-EVT-08.8, REQ-EVT-08.9, REQ-EVT-08.10, REQ-EVT-08.11, REQ-EVT-09.1, REQ-EVT-09.2, REQ-EVT-17.1, REQ-EVT-17.5, REQ-EVT-17.6, REQ-EVT-17.7, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05, REQ-EVT-B06_

### 12. Property-based test opzionali

- [ ]* 12.1 Aggiungere Hypothesis come dipendenza esclusivamente di test
  - Integrare `requirements.txt` con un pin esatto di `hypothesis`, senza aggiungere dipendenze runtime; mantenere i test parametrizzati pytest come suite obbligatoria e usare Hypothesis solo per le property universali del design.
  - _Requirements: REQ-EVT-03.1, REQ-EVT-16.4, REQ-EVT-17.7_

- [ ]* 12.2 Scrivere il property test per creazione e default
  - Creare `tests/unit/test_property_01_creation.py` con strategie per body validi e verificare preservazione input, default, UUID v4 e timestamp UTC.
  - **Property 1: La creazione preserva l'input e applica i default**
  - **Validates: Requirements 3.3, 3.15, 4.1, 4.2, 4.4**
  - _Requirements: REQ-EVT-03.3, REQ-EVT-03.15, REQ-EVT-04.1, REQ-EVT-04.2, REQ-EVT-04.4_

- [ ]* 12.3 Scrivere il property test per input non valido
  - Creare `tests/unit/test_property_02_invalid_input.py` e generare violazioni singole dei vincoli, verificando sempre `ValidationError`/422 `VALIDATION_ERROR`.
  - **Property 2: L'input non valido viene sempre rifiutato con 422**
  - **Validates: Requirements 3.1–3.10, 3.12, 4.6, 17.8**
  - _Requirements: REQ-EVT-03.1, REQ-EVT-03.2, REQ-EVT-03.4, REQ-EVT-03.5, REQ-EVT-03.6, REQ-EVT-03.7, REQ-EVT-03.8, REQ-EVT-03.9, REQ-EVT-03.10, REQ-EVT-03.12, REQ-EVT-04.6, REQ-EVT-17.8_

- [ ]* 12.4 Scrivere il property test per campi vietati
  - Creare `tests/unit/test_property_03_forbidden_fields.py` e generare campi read-only o sconosciuti in POST/PUT/PATCH, verificando il rifiuto uniforme.
  - **Property 3: I campi read-only e i campi sconosciuti sono sempre rifiutati**
  - **Validates: Requirements 3.13, 3.14**
  - _Requirements: REQ-EVT-03.13, REQ-EVT-03.14_

- [ ]* 12.5 Scrivere il property test per `price`
  - Creare `tests/unit/test_property_04_price.py` con valori validi, negativi e con oltre due decimali, verificando validazione e rappresentazione numerica normalizzata.
  - **Property 4: `price` è sempre non negativo con due decimali**
  - **Validates: Requirements 3.10, 3.11, 17.4**
  - _Requirements: REQ-EVT-03.10, REQ-EVT-03.11, REQ-EVT-17.4_

- [ ]* 12.6 Scrivere il property test per organizzatore inesistente
  - Creare `tests/unit/test_property_05_reference_not_found.py` e generare body validi per POST/PUT/PATCH con client che segnala riferimento assente, verificando l'interruzione dell'operazione.
  - **Property 5: Organizzatore inesistente produce sempre 422 REFERENCE_NOT_FOUND**
  - **Validates: Requirements 10.2, 10.3, 10.4, 10.5**
  - _Requirements: REQ-EVT-10.2, REQ-EVT-10.3, REQ-EVT-10.4, REQ-EVT-10.5, REQ-EVT-B01_

- [ ]* 12.7 Scrivere il property test per ruolo organizzatore
  - Creare `tests/unit/test_property_06_organizer_role.py` e generare ruoli presenti, diversi o assenti, accettando solo `organizer`.
  - **Property 6: Organizzatore con ruolo errato produce sempre 422 INVALID_ORGANIZER**
  - **Validates: Requirements 11.1, 11.2**
  - _Requirements: REQ-EVT-11.1, REQ-EVT-11.2, REQ-EVT-B02_

- [ ]* 12.8 Scrivere il property test per coerenza delle date
  - Creare `tests/unit/test_property_07_dates.py` con coppie di date valide e merge PATCH, verificando l'invariante `end_date >= start_date`.
  - **Property 7: La coerenza delle date è un invariante**
  - **Validates: Requirements 12.1, 12.2, 12.3**
  - _Requirements: REQ-EVT-12.1, REQ-EVT-12.2, REQ-EVT-12.3, REQ-EVT-B03_

- [ ]* 12.9 Scrivere il property test per transizioni di stato
  - Creare `tests/unit/test_property_08_transitions.py` su tutte le coppie di stato, distinguendo transizioni ammesse, invalide e idempotenti.
  - **Property 8: Solo le transizioni ammesse sono accettate**
  - **Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5**
  - _Requirements: REQ-EVT-13.1, REQ-EVT-13.2, REQ-EVT-13.3, REQ-EVT-13.4, REQ-EVT-13.5, REQ-EVT-B04_

- [ ]* 12.10 Scrivere il property test per indisponibilità della dipendenza
  - Creare `tests/unit/test_property_09_dependency.py` sulle modalità timeout, connessione e 5xx, verificando sempre `DependencyUnavailableError`/503.
  - **Property 9: Il fallimento della dipendenza produce sempre 503**
  - **Validates: Requirements 14.1, 14.2, 14.3, 14.4**
  - _Requirements: REQ-EVT-14.1, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-14.4, REQ-EVT-B05_

- [ ]* 12.11 Scrivere il property test per filtri e total
  - Creare `tests/unit/test_property_10_filters.py` con collezioni e combinazioni di filtri generate, verificando precisione, completezza, AND e `total` pre-paginazione.
  - **Property 10: I filtri di lista sono completi, precisi e con `total` corretto**
  - **Validates: Requirements 15.1, 15.2, 15.3, 15.4, 5.1, 5.8**
  - _Requirements: REQ-EVT-05.1, REQ-EVT-05.8, REQ-EVT-15.1, REQ-EVT-15.2, REQ-EVT-15.3, REQ-EVT-15.4, REQ-EVT-B06_

- [ ]* 12.12 Scrivere il property test per paginazione
  - Creare `tests/unit/test_property_11_pagination.py` con collezioni, pagine e dimensioni valide generate, verificando segmento, limiti, default e pagina vuota.
  - **Property 11: La paginazione rispetta i suoi invarianti**
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.9, 15.5**
  - _Requirements: REQ-EVT-05.1, REQ-EVT-05.2, REQ-EVT-05.3, REQ-EVT-05.9, REQ-EVT-15.5_

- [ ]* 12.13 Scrivere il property test per round-trip GET
  - Creare `tests/unit/test_property_12_round_trip.py` e verificare che ogni Event creato sia rileggibile invariato e che identificativi assenti producano `NOT_FOUND`.
  - **Property 12: Round-trip GET dopo creazione**
  - **Validates: Requirements 6.1, 6.2, 6.3**
  - _Requirements: REQ-EVT-06.1, REQ-EVT-06.2, REQ-EVT-06.3_

- [ ]* 12.14 Scrivere il property test per merge PATCH
  - Creare `tests/unit/test_property_13_patch.py` con sottoinsiemi non vuoti di campi scrivibili e verificare che cambino solo i campi presenti più `updated_at`.
  - **Property 13: PATCH aggiorna solo i campi presenti nel body**
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
  - _Requirements: REQ-EVT-08.1, REQ-EVT-08.2, REQ-EVT-08.3, REQ-EVT-08.4_

- [ ]* 12.15 Scrivere il property test per sostituzione PUT
  - Creare `tests/unit/test_property_14_put.py` con body completi validi, verificando sostituzione, default specifici e preservazione dei campi immutabili.
  - **Property 14: PUT sostituisce i campi scrivibili preservando id/created_at**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
  - _Requirements: REQ-EVT-07.1, REQ-EVT-07.2, REQ-EVT-07.3, REQ-EVT-07.4, REQ-EVT-07.5_

- [ ]* 12.16 Scrivere il property test per eliminazione
  - Creare `tests/unit/test_property_15_delete.py` e verificare che DELETE renda ogni Event creato irraggiungibile e segnali identificativi inesistenti.
  - **Property 15: DELETE rende l'Event irraggiungibile**
  - **Validates: Requirements 9.1, 9.2**
  - _Requirements: REQ-EVT-09.1, REQ-EVT-09.2_

- [ ]* 12.17 Scrivere il property test per equivalenza dei backend
  - Creare `tests/unit/test_property_16_backends.py` con sequenze CRUD generate e directory isolate, normalizzando i valori non deterministici e confrontando i risultati logici di memory, JSON e SQLite.
  - **Property 16: I tre backend producono risultati equivalenti**
  - **Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5**
  - _Requirements: REQ-EVT-16.1, REQ-EVT-16.2, REQ-EVT-16.3, REQ-EVT-16.4, REQ-EVT-16.5_

### 13. Test di integrazione con user-service reale

- [ ] 13.1 Implementare l'harness dei servizi reali
  - Creare `tests/integration/conftest.py` per trovare porte libere con `socket`, avviare user-service ed event-service tramite `subprocess.Popen([sys.executable, "-m", "app"])`, iniettare `PORT`, `USER_SERVICE_URL` e backend memory, attendere `/health` con polling limitato e garantire teardown `terminate`/`kill`. Non mockare il traffico HTTP.
  - _Requirements: REQ-EVT-01.1, REQ-EVT-01.4, REQ-EVT-02.1, REQ-EVT-14.1, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

- [ ] 13.2 Implementare il caso positivo IT-E01
  - Creare `tests/integration/test_it_e01_create_event.py`: creare un organizer reale su user-service, creare un Event reale su event-service e verificare 201, `Location` e risorsa conforme.
  - _Requirements: REQ-EVT-04.1, REQ-EVT-04.3, REQ-EVT-10.1, REQ-EVT-10.2, REQ-EVT-11.1, REQ-EVT-B01, REQ-EVT-B02_

- [ ] 13.3 Implementare il caso riferimento inesistente IT-E02
  - Creare `tests/integration/test_it_e02_reference_not_found.py`: inviare un UUID organizzatore non presente e verificare 422 con codice `REFERENCE_NOT_FOUND`, senza creazione dell'Event.
  - _Requirements: REQ-EVT-10.5, REQ-EVT-B01_

- [ ] 13.4 Implementare il caso ruolo errato IT-E03
  - Creare `tests/integration/test_it_e03_invalid_organizer.py`: creare un attendee reale, usarlo come organizzatore e verificare 422 con codice `INVALID_ORGANIZER`.
  - _Requirements: REQ-EVT-11.2, REQ-EVT-B02_

- [ ] 13.5 Implementare il caso dipendenza spenta IT-E08
  - Creare `tests/integration/test_it_e08_dependency_unavailable.py`: avviare solo event-service con `USER_SERVICE_URL` verso una porta libera non in ascolto e verificare 503 con codice `DEPENDENCY_UNAVAILABLE`, usando teardown robusto e nessun mock HTTP.
  - _Requirements: REQ-EVT-07.10, REQ-EVT-08.11, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-B05_

### 14. Validazione finale

- [ ] 14.1 Eseguire la suite unit con soglia di coverage
  - Dalla root `services/event_service`, eseguire `pytest tests/unit --cov=app --cov-report=term-missing --cov-fail-under=80` e correggere esclusivamente il codice di event-service finché tutti i test obbligatori passano.
  - _Requirements: REQ-EVT-01.1–REQ-EVT-17.9, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05, REQ-EVT-B06_

- [ ] 14.2 Eseguire i test di integrazione propri
  - Dalla root del servizio, eseguire `pytest tests/integration -v` e verificare il completamento di IT-E01, IT-E02, IT-E03 e IT-E08 senza processi residui.
  - _Requirements: REQ-EVT-04.1, REQ-EVT-10.5, REQ-EVT-11.2, REQ-EVT-14.2, REQ-EVT-14.3, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05_

- [ ] 14.3 Eseguire il subset di collaudo docente per event-service
  - Dalla root del repository, eseguire `pytest tests/integration -m mandatory -k event -v`, analizzare eventuali regressioni e non modificare i test in `tests/integration`.
  - _Requirements: REQ-EVT-02.1, REQ-EVT-04.1, REQ-EVT-05.1, REQ-EVT-06.1, REQ-EVT-07.1, REQ-EVT-08.1, REQ-EVT-09.1, REQ-EVT-17.7, REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B03, REQ-EVT-B04, REQ-EVT-B05, REQ-EVT-B06_

- [ ] 14.4 Verificare l'integrità dei file protetti
  - Dalla root del repository, eseguire `sha256sum -c CHECKSUMS.sha256` o l'equivalente PowerShell e confermare che contratti e test protetti siano invariati.
  - _Requirements: REQ-EVT-17.6, REQ-EVT-17.7_

## Notes

- I task sono prompt incrementali per un code-generation LLM: ogni attività usa gli artefatti delle wave precedenti e il wiring finale elimina codice orfano.
- I task contrassegnati con `*` sono opzionali e riguardano esclusivamente Hypothesis e le 16 property del design; i test pytest parametrizzati restano obbligatori e non ampliano lo stack base.
- Le regole `REQ-EVT-B01`–`REQ-EVT-B06` devono comparire nei commenti/docstring pertinenti del Service Layer e nei marker o nomi dei test per la tracciabilità d'esame.
- `contracts/openapi/event-service.yaml`, `contracts/validator.py`, `tests/integration`, `requirements.md`, `design.md` e i servizi esistenti non devono essere modificati durante l'implementazione di questo piano.
- `services.yaml` deve essere soltanto verificato dal task 1.6; il piano non prevede di sovrascriverlo.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["3.2", "4.2"] },
    { "id": 4, "tasks": ["4.3"] },
    { "id": 5, "tasks": ["4.4"] },
    { "id": 6, "tasks": ["4.5"] },
    { "id": 7, "tasks": ["5.1"] },
    { "id": 8, "tasks": ["5.2"] },
    { "id": 9, "tasks": ["5.3"] },
    { "id": 10, "tasks": ["5.4"] },
    { "id": 11, "tasks": ["5.5"] },
    { "id": 12, "tasks": ["5.6"] },
    { "id": 13, "tasks": ["5.7"] },
    { "id": 14, "tasks": ["6.1"] },
    { "id": 15, "tasks": ["6.2"] },
    { "id": 16, "tasks": ["6.3"] },
    { "id": 17, "tasks": ["6.4"] },
    { "id": 18, "tasks": ["6.5"] },
    { "id": 19, "tasks": ["6.6"] },
    { "id": 20, "tasks": ["6.7"] },
    { "id": 21, "tasks": ["6.8"] },
    { "id": 22, "tasks": ["7.1", "7.2", "12.1"] },
    { "id": 23, "tasks": ["8.1", "9.1", "10.1", "10.2", "10.3", "10.4", "10.5", "11.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8", "12.9", "12.10", "12.11", "12.12", "12.13", "12.14", "12.15", "12.16", "12.17", "13.1"] },
    { "id": 24, "tasks": ["13.2", "13.3", "13.4", "13.5"] },
    { "id": 25, "tasks": ["14.1", "14.2", "14.3", "14.4"] }
  ]
}
```
