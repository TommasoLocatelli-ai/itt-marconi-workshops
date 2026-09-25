# Implementation Plan: user-service

## Panoramica

Implementazione del microservizio anagrafica `user-service` della piattaforma TechConf.
Il servizio espone API REST per il ciclo di vita degli utenti (`attendee`, `speaker`,
`organizer`) ed è strutturato in tre livelli nettamente separati: **Router** → **Service
Layer** → **Repository**, con supporto a tre backend di persistenza intercambiabili
(`memory`, `json`, `sqlite`).

Porta di ascolto: `PORT` (default `5001`). Base path: `/api/v1/users`.

---

## Task

- [ ] 1. Setup struttura del servizio e configurazione

  - Creare la directory `services/user_service/` con la struttura completa a tre livelli:
    `app/`, `tests/unit/`, `tests/integration/`
  - Creare `app/__init__.py` con la factory `create_app(repo=None)` che accetta un
    repository opzionale per dependency injection nei test
  - Creare `app/config.py` che legge esclusivamente da variabili d'ambiente: `PORT`
    (default `5001`), `STORAGE_BACKEND` (default `memory`), `DATA_DIR` (default `./data`)
  - Creare `run.py` nella root del servizio che importa `create_app` e avvia Flask sulla
    porta letta da `config.PORT`
  - Creare `requirements.txt` con le dipendenze runtime (`flask`, `requests`) e di test
    (`pytest`, `pytest-cov`, `responses`, `hypothesis`)
  - Aggiungere la voce `user_service` in `services.yaml` con `cwd: services/user_service`
    e `command: python run.py`
  - _Requirements: REQ-USR-01_

- [ ] 2. Modelli dati ed eccezioni

  - [ ] 2.1 Creare `app/models.py` con la dataclass `User`
    - Campi: `id` (str), `first_name` (str), `last_name` (str), `email` (str, sempre
      lowercase), `role` (str, enum), `created_at` (str ISO 8601 UTC), `updated_at`
      (str ISO 8601 UTC), `company` (Optional[str])
    - Metodo `to_dict()` che omette i campi `None` (tranne `company`)
    - _Requirements: REQ-USR-03, REQ-USR-13_

  - [ ] 2.2 Creare `app/exceptions.py` con le eccezioni custom
    - `ValidationError(field: str, message: str)` — mappata a 422
    - `EmailAlreadyExistsError(message: str)` — mappata a 409
    - `NotFoundError(message: str)` — mappata a 404
    - _Requirements: REQ-USR-03, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-08_

- [ ] 3. Repository Pattern — interfaccia e backend

  - [ ] 3.1 Creare la classe base `UserRepository` in `app/repository.py`
    - Interfaccia comune con metodi: `find_by_id(id: str) -> dict | None`,
      `find_all(filters: dict) -> list[dict]`, `save(user: dict) -> dict`,
      `delete(id: str) -> bool`, `email_exists(email: str, exclude_id: str | None) -> bool`
    - _Requirements: REQ-USR-12_

  - [ ] 3.2 Implementare `MemoryRepository`
    - Struttura dati: `dict` Python `{id: user_dict}`
    - Tutti e cinque i metodi dell'interfaccia
    - `email_exists` con confronto case-insensitive (`u['email'] == email`)
    - _Requirements: REQ-USR-12_

  - [ ] 3.3 Implementare `JsonRepository`
    - File: `{DATA_DIR}/users.json`, formato `{"users": [...]}`
    - Strategia atomic read-modify-write (write temporaneo + rename) usando solo `json`
      dalla stdlib
    - Tutti e cinque i metodi dell'interfaccia
    - _Requirements: REQ-USR-12_

  - [ ] 3.4 Implementare `SqliteRepository`
    - File: `{DATA_DIR}/users.db`
    - Schema: `CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, first_name TEXT
      NOT NULL, last_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, company TEXT,
      role TEXT NOT NULL DEFAULT 'attendee', created_at TEXT NOT NULL, updated_at
      TEXT NOT NULL)`
    - Connessione aperta e chiusa per ogni operazione; solo stdlib `sqlite3`
    - Tutti e cinque i metodi dell'interfaccia
    - _Requirements: REQ-USR-12_

  - [ ] 3.5 Implementare `get_repository()` factory
    - Legge `STORAGE_BACKEND` da `config.py` (non da `os.environ` direttamente)
    - Fallback a `MemoryRepository` per valori non riconosciuti (REQ-USR-01.7)
    - _Requirements: REQ-USR-01, REQ-USR-12_

- [ ] 4. Checkpoint — Verificare il Repository Pattern
  - Assicurarsi che tutti e tre i backend siano istanziabili senza errori; chiedere
    all'utente se ci sono dubbi prima di procedere con il Service Layer.

- [ ] 5. Service Layer — logica di business

  - [ ] 5.1 Creare `UserService(repo: UserRepository)` in `app/service.py` con `create_user`
    - Validare i campi obbligatori: `first_name` (1–50 car.), `last_name` (1–50 car.),
      `email` (formato email); `company` (max 100 car. se presente); `role` tra i valori
      ammessi; campo `id` nel body ignorato o rifiutato con ValidationError
    - Normalizzare `email` in minuscolo **[REQ-USR-B02]**
    - Controllare unicità con `repo.email_exists(email, exclude_id=None)` **[REQ-USR-B01]**
    - Assegnare `role` default `attendee` se assente
    - Generare `id` UUID v4 e `created_at`/`updated_at` ISO 8601 UTC
    - Chiamare `repo.save(user_dict)` e restituire il dict
    - _Requirements: REQ-USR-03, REQ-USR-09, REQ-USR-10_

  - [ ]* 5.2 Scrivere property test per `create_user` (Property 1)
    - **Property 1: Creazione preserva i dati di input**
    - **Validates: Requirements REQ-USR-03**

  - [ ]* 5.3 Scrivere property test per unicità email in `create_user` (Property 2)
    - **Property 2: Unicità email è invariante case-insensitive**
    - **Validates: Requirements REQ-USR-03, REQ-USR-09**

  - [ ]* 5.4 Scrivere property test per normalizzazione email (Property 3)
    - **Property 3: Normalizzazione email è un'invariante di salvataggio**
    - **Validates: Requirements REQ-USR-10**

  - [ ] 5.5 Implementare `list_users(filters: dict, page: int, page_size: int) -> dict`
    - Passare `filters` a `repo.find_all(filters)` con filtri per `role` e/o `email` in
      AND logico **[REQ-USR-B03]**
    - Calcolare `total` sul risultato filtrato (non sul totale assoluto)
    - Applicare la paginazione: restituire la slice `[(page-1)*page_size : page*page_size]`
    - Restituire `{"items": [...], "page": page, "page_size": page_size, "total": total}`
    - _Requirements: REQ-USR-04, REQ-USR-11_

  - [ ]* 5.6 Scrivere property test per filtro per ruolo (Property 4)
    - **Property 4: Filtro per ruolo è completo e preciso**
    - **Validates: Requirements REQ-USR-04, REQ-USR-11**

  - [ ]* 5.7 Scrivere property test per filtro per email (Property 5)
    - **Property 5: Filtro per email è completo e preciso (case-insensitive)**
    - **Validates: Requirements REQ-USR-04, REQ-USR-11**

  - [ ]* 5.8 Scrivere property test per filtri combinati (Property 6)
    - **Property 6: Filtri combinati applicano AND logico**
    - **Validates: Requirements REQ-USR-04, REQ-USR-11**

  - [ ] 5.9 Implementare `get_user(id: str) -> dict`
    - Chiamare `repo.find_by_id(id)`; sollevare `NotFoundError` se `None`
    - _Requirements: REQ-USR-05_

  - [ ]* 5.10 Scrivere property test per round-trip GET (Property 7)
    - **Property 7: Round-trip GET dopo creazione**
    - **Validates: Requirements REQ-USR-05**

  - [ ] 5.11 Implementare `replace_user(id: str, data: dict) -> dict`
    - Verificare esistenza utente (NotFoundError se assente)
    - Validare tutti i campi come in `create_user`; `role` default `attendee` se assente
    - Normalizzare email; controllare unicità escludendo l'`id` corrente **[REQ-USR-B01,
      REQ-USR-B02]**
    - Preservare `id` e `created_at` originali; aggiornare `updated_at`
    - _Requirements: REQ-USR-06_

  - [ ]* 5.12 Scrivere property test per PUT (Property 8)
    - **Property 8: PUT sostituisce integralmente i campi scrivibili**
    - **Validates: Requirements REQ-USR-06**

  - [ ] 5.13 Implementare `update_user(id: str, data: dict) -> dict`
    - Verificare esistenza utente (NotFoundError se assente)
    - Aggiornare solo i campi presenti nel body; validare i vincoli solo sui campi forniti
    - Normalizzare `email` se presente nel body; controllare unicità escludendo `id`
      **[REQ-USR-B01, REQ-USR-B02]**
    - Aggiornare `updated_at`
    - _Requirements: REQ-USR-07_

  - [ ]* 5.14 Scrivere property test per PATCH (Property 9)
    - **Property 9: PATCH aggiorna solo i campi presenti nel body**
    - **Validates: Requirements REQ-USR-07**

  - [ ] 5.15 Implementare `delete_user(id: str) -> None`
    - Chiamare `repo.find_by_id(id)` → NotFoundError se assente
    - Chiamare `repo.delete(id)`
    - _Requirements: REQ-USR-08_

  - [ ]* 5.16 Scrivere property test per DELETE (Property 10)
    - **Property 10: DELETE rende l'utente irrecuperabile**
    - **Validates: Requirements REQ-USR-08**

- [ ] 6. Checkpoint — Verificare il Service Layer
  - Assicurarsi che tutti i metodi del Service Layer siano implementati e che le regole
    B01, B02, B03 funzionino correttamente; chiedere all'utente se ci sono dubbi.

- [ ] 7. Router Flask — endpoint HTTP

  - [ ] 7.1 Creare `app/routes.py` con Blueprint e `GET /health`
    - Istanziare `Blueprint('api', __name__)`
    - Implementare `GET /health` che restituisce
      `{"status": "ok", "service": "user-service"}` con status 200
    - Registrare gli error handler sul Blueprint per `ValidationError` (422),
      `EmailAlreadyExistsError` (409), `NotFoundError` (404), `BadRequest` (400)
    - Formato errore standard: `{"error": {"code": "...", "message": "...", "details": {}}}`
    - _Requirements: REQ-USR-02, REQ-USR-13_

  - [ ] 7.2 Implementare `POST /api/v1/users`
    - `request.get_json(force=True, silent=False)` → 400 se malformato
    - Delegare a `service.create_user(data)`
    - Rispondere 201 con body della risorsa e header `Location: /api/v1/users/{id}`
    - _Requirements: REQ-USR-03_

  - [ ] 7.3 Implementare `GET /api/v1/users`
    - Estrarre e validare `page` (default `1`, intero ≥ 1), `page_size` (default `20`,
      intero ≥ 1 e ≤ 100), `role` (enum valido), `email` dai query params → 422 se invalidi
    - Delegare a `service.list_users(filters, page, page_size)`
    - _Requirements: REQ-USR-04, REQ-USR-11_

  - [ ] 7.4 Implementare `GET /api/v1/users/<id>`
    - Delegare a `service.get_user(id)`; l'error handler gestisce NotFoundError → 404
    - _Requirements: REQ-USR-05_

  - [ ] 7.5 Implementare `PUT /api/v1/users/<id>`
    - Parsing body con `get_json`; delegare a `service.replace_user(id, data)`
    - Rispondere 200 con la risorsa aggiornata
    - _Requirements: REQ-USR-06_

  - [ ] 7.6 Implementare `PATCH /api/v1/users/<id>`
    - Parsing body con `get_json`; delegare a `service.update_user(id, data)`
    - Rispondere 200 con la risorsa aggiornata
    - _Requirements: REQ-USR-07_

  - [ ] 7.7 Implementare `DELETE /api/v1/users/<id>`
    - Delegare a `service.delete_user(id)`
    - Rispondere 204 senza body
    - _Requirements: REQ-USR-08_

- [ ] 8. Checkpoint — Verificare il Router
  - Assicurarsi che tutti gli endpoint rispondano con i codici HTTP corretti e che gli
    error handler siano registrati; chiedere all'utente se ci sono dubbi.

- [ ] 9. Test unitari

  - [ ] 9.1 Creare `tests/conftest.py` con le fixture base
    - Fixture `app`: crea l'applicazione Flask con `MemoryRepository` (per isolamento)
    - Fixture `client`: restituisce il test client Flask
    - Fixture `repo` parametrizzata su `["memory", "json", "sqlite"]` con `tmp_path` e
      `monkeypatch` per `STORAGE_BACKEND` e `DATA_DIR`
    - Creare `pytest.ini` con il marker `req` per la tracciabilità dei requisiti
    - _Requirements: REQ-USR-01, REQ-USR-12_

  - [ ] 9.2 Creare `tests/unit/test_repository.py`
    - CRUD completo parametrizzato sui tre backend usando la fixture `repo`
    - `test_save_and_find_by_id`, `test_find_all_no_filter`, `test_delete_removes_user`,
      `test_email_exists_case_insensitive`, `test_find_all_with_role_filter`,
      `test_find_all_with_email_filter`
    - _Requirements: REQ-USR-12_

  - [ ]* 9.3 Scrivere property test per equivalenza dei tre backend (Property 11)
    - **Property 11: I tre backend producono risultati equivalenti**
    - **Validates: Requirements REQ-USR-12**

  - [ ] 9.4 Creare `tests/unit/test_service.py`
    - Verificare **REQ-USR-B01** (unicità email): `test_create_raises_email_exists_when_duplicate`
    - Verificare **REQ-USR-B02** (normalizzazione): `test_create_normalizes_email_to_lowercase`,
      `test_replace_normalizes_email`, `test_patch_normalizes_email`
    - Verificare **REQ-USR-B03** (filtri): `test_list_applies_role_filter`,
      `test_list_applies_email_filter_case_insensitive`, `test_list_applies_combined_filters`
    - Verificare `delete_user` solleva `NotFoundError` per id inesistente
    - Repository mockato con `unittest.mock.MagicMock`
    - _Requirements: REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07,
      REQ-USR-08, REQ-USR-09, REQ-USR-10, REQ-USR-11_

  - [ ] 9.5 Creare `tests/unit/test_routes.py`
    - Per ogni endpoint: almeno 1 caso positivo (happy path) + principali casi di errore
    - Includere almeno 1 chiamata `assert_matches_contract("user", method, path, resp)`
      per endpoint; importare il validator con `sys.path.insert`
    - Service layer mockato con `unittest.mock.patch`
    - Endpoint coperti: `GET /health`, `POST /api/v1/users` (201, 400, 409, 422),
      `GET /api/v1/users` (200, 422), `GET /api/v1/users/<id>` (200, 404),
      `PUT /api/v1/users/<id>` (200, 404, 409, 422), `PATCH /api/v1/users/<id>`
      (200, 404, 409, 422), `DELETE /api/v1/users/<id>` (204, 404)
    - _Requirements: REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06,
      REQ-USR-07, REQ-USR-08, REQ-USR-13_

  - [ ] 9.6 Creare `tests/unit/test_properties.py` con Hypothesis
    - Importare `from hypothesis import given, settings` e `from hypothesis.strategies import ...`
    - Ogni property usa `@settings(max_examples=100)` e docstring con tag
      `Feature: user-service, Property N: <testo>`
    - Property 1 (`test_create_preserves_input`): dato un input valido, la risorsa
      restituita contiene esattamente i valori forniti
    - Property 2 (`test_duplicate_email_always_rejected`): qualsiasi variante
      maiuscola/minuscola di un'email già registrata causa 409
    - Property 3 (`test_email_always_stored_lowercase`): l'email restituita è sempre
      in minuscolo
    - Property 4 (`test_role_filter_is_complete_and_precise`): la risposta contiene
      solo utenti con il ruolo richiesto e `total` è corretto
    - Property 5 (`test_email_filter_is_case_insensitive`): la risposta contiene solo
      utenti con email corrispondente (case-insensitive) e `total` è corretto
    - Property 6 (`test_combined_filters_apply_and_logic`): tutti gli utenti restituiti
      soddisfano entrambi i criteri
    - Property 7 (`test_get_after_create_roundtrip`): GET restituisce esattamente la
      stessa risorsa creata
    - Property 8 (`test_put_replaces_writable_fields`): PUT aggiorna i campi scrivibili,
      preserva `id` e `created_at`, aggiorna `updated_at`
    - Property 9 (`test_patch_updates_only_present_fields`): PATCH modifica solo i
      campi nel body, lascia invariati gli altri
    - Property 10 (`test_delete_makes_user_unreachable`): dopo DELETE il GET restituisce 404
    - Property 11 (`test_backends_produce_equivalent_results`): stessa sequenza CRUD
      produce risultati equivalenti sui tre backend
    - _Requirements: REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07,
      REQ-USR-08, REQ-USR-09, REQ-USR-10, REQ-USR-11, REQ-USR-12_

- [ ] 10. Checkpoint finale — Verificare coverage e suite di collaudo
  - Eseguire `pytest tests/unit --cov=app --cov-report=term-missing` e verificare
    coverage ≥ 80%
  - Eseguire `pytest tests/integration -m mandatory -v` dalla root del repo per
    verificare il superamento dei test obbligatori del docente
  - Correggere eventuali regressioni prima di considerare il task completato

---

## Note

- I task contrassegnati con `*` sono opzionali e possono essere saltati per un MVP più rapido
- I property-based test vanno in `tests/unit/test_properties.py`; usano `MemoryRepository`
  direttamente (senza Flask client) per velocità di esecuzione
- Ogni property test usa il tag `Feature: user-service, Property N: <testo>` nel docstring
  per la tracciabilità verso il design document
- Il marker `@pytest.mark.req("REQ-USR-B01")` va aggiunto ai test di regressione delle
  regole di business per facilitare il grep
- Il validator del contratto si importa con `sys.path.insert(0, <path-to-root>)` per
  evitare modifiche ai `requirements.txt`

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["3.5"] },
    { "id": 4, "tasks": ["5.1", "5.5", "5.9", "5.11", "5.13", "5.15"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "5.6", "5.7", "5.8", "5.10", "5.12", "5.14", "5.16"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4", "7.5", "7.6", "7.7"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2", "9.4", "9.5"] },
    { "id": 10, "tasks": ["9.3", "9.6"] }
  ]
}
```
