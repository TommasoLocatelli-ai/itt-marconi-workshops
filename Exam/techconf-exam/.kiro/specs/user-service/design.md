# Design Document — user-service

## Overview

Il **user-service** è il microservizio anagrafica della piattaforma TechConf.
Espone un'API REST per la gestione del ciclo di vita degli utenti (`attendee`,
`speaker`, `organizer`) ed è la **fonte di verità** per le identità all'interno
del sistema. Gli altri microservizi (`event-service`, `registration-service`,
`notification-service`) lo chiamano per verificare l'esistenza di un utente, ma
esso stesso **non chiama** altri servizi.

Porta di ascolto: `PORT` (default `5001` in sviluppo).  
Base path: `/api/v1/users`.  
Contratto definitivo: `contracts/openapi/user-service.yaml`.

Requisiti coperti: REQ-USR-01 … REQ-USR-13 (regole di business: REQ-USR-B01,
REQ-USR-B02, REQ-USR-B03).

---

## Architecture

Il servizio è strutturato in **tre livelli nettamente separati**, come prescritto
dalla struttura comune del repository (`structure.md`):

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Client                          │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP Request
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Router  (routes.py)                       │
│  • Parsing body JSON                                        │
│  • Validazione tipi HTTP (campi obbligatori, formati base)  │
│  • Costruzione risposta (status code, header Location)      │
│  • Mappatura eccezioni → JSON error                         │
│  • NESSUNA regola di business REQ-USR-B*                    │
└────────────────────────────┬────────────────────────────────┘
                             │ chiama metodi Python
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Service Layer  (service.py)                 │
│  • Implementa tutte le regole REQ-USR-B*                    │
│  • Normalizzazione email (B02), unicità (B01), filtri (B03) │
│  • Generazione UUID v4, timestamps ISO 8601 UTC             │
│  • Non conosce Flask, non costruisce Response               │
│  • Riceve il repository per dependency injection            │
└────────────────────────────┬────────────────────────────────┘
                             │ chiama interfaccia Repository
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               Repository  (repository.py)                   │
│  • Unico punto che conosce STORAGE_BACKEND                  │
│  ┌───────────────┐ ┌────────────────┐ ┌──────────────────┐  │
│  │MemoryRepository│ │JsonRepository  │ │SqliteRepository  │  │
│  └───────────────┘ └────────────────┘ └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Flusso di una richiesta tipo — `POST /api/v1/users`

```
Client
  │
  │ POST /api/v1/users  {first_name, last_name, email, role}
  ▼
routes.py
  ├── request.get_json(force=True, silent=False)  → 400 se malformato
  ├── valida campi obbligatori presenti            → 422 se assenti
  └── chiama service.create_user(data)
        ▼
      service.py
        ├── normalizza email.lower()               [REQ-USR-B02]
        ├── controlla repo.email_exists(email)     [REQ-USR-B01]
        │     └── EmailAlreadyExistsError           → propagata al router
        ├── genera uuid4(), created_at, updated_at
        └── chiama repo.save(user_dict)
              ▼
            repository.py  (backend attivo)
              └── inserisce il record → restituisce user_dict
        ▲
      service.py restituisce user_dict
  ▲
routes.py
  ├── costruisce risposta 201
  ├── imposta header Location: /api/v1/users/{id}
  └── return jsonify(user_dict), 201
```

---

## Components and Interfaces

### `app/__init__.py` — Factory

```python
def create_app(repo=None) -> Flask:
    app = Flask(__name__)
    if repo is None:
        repo = get_repository()
    from .routes import bp
    bp.repo = repo          # dependency injection
    app.register_blueprint(bp)
    return app
```

La factory accetta un repository opzionale per i test (dependency injection esplicita).

---

### `app/config.py` — Configurazione

Legge **tutte** le variabili d'ambiente; nessun'altra parte del codice chiama
`os.environ` direttamente.

| Variabile | Default | Uso |
|---|---|---|
| `PORT` | `5001` | Porta Flask |
| `STORAGE_BACKEND` | `memory` | Backend persistenza |
| `DATA_DIR` | `./data` | Directory file json/sqlite |
| `USER_SERVICE_URL` | `http://localhost:5001` | (self-reference, usato raramente) |

---

### `app/models.py` — Modello dati

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class User:
    id: str
    first_name: str
    last_name: str
    email: str            # sempre lowercase
    role: str             # 'attendee' | 'speaker' | 'organizer'
    created_at: str       # ISO 8601 UTC
    updated_at: str       # ISO 8601 UTC
    company: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None or k == 'company'}
```

---

### `app/exceptions.py` — Eccezioni custom

```python
class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)

class EmailAlreadyExistsError(Exception):
    pass

class NotFoundError(Exception):
    pass
```

---

### `app/routes.py` — Router Flask Blueprint

```
Blueprint: bp  (prefix non configurato; gli endpoint includono il path completo)

Endpoint registrati:
  GET    /health
  POST   /api/v1/users
  GET    /api/v1/users
  GET    /api/v1/users/<id>
  PUT    /api/v1/users/<id>
  PATCH  /api/v1/users/<id>
  DELETE /api/v1/users/<id>

Error handlers registrati sul Blueprint:
  ValidationError        → 422  VALIDATION_ERROR
  EmailAlreadyExistsError→ 409  EMAIL_ALREADY_EXISTS
  NotFoundError          → 404  NOT_FOUND
  BadRequest (Flask)     → 400  MALFORMED_JSON
```

Responsabilità del router per ogni endpoint:

| Endpoint | Responsabilità router |
|---|---|
| `GET /health` | Restituisce direttamente `{"status":"ok","service":"user-service"}` |
| `POST /api/v1/users` | Parsing body, delega a `service.create_user()`, risponde 201 + Location |
| `GET /api/v1/users` | Estrae e valida `page`, `page_size`, `role`, `email` dai query params; delega a `service.list_users()` |
| `GET /api/v1/users/<id>` | Delega a `service.get_user(id)` |
| `PUT /api/v1/users/<id>` | Parsing body, delega a `service.replace_user(id, data)` |
| `PATCH /api/v1/users/<id>` | Parsing body (ammette campi parziali), delega a `service.update_user(id, data)` |
| `DELETE /api/v1/users/<id>` | Delega a `service.delete_user(id)`, risponde 204 senza body |

---

### `app/service.py` — Service Layer

```
UserService(repo: UserRepository)

Metodi pubblici:
  create_user(data: dict) -> dict
  list_users(filters: dict, page: int, page_size: int) -> dict
  get_user(id: str) -> dict
  replace_user(id: str, data: dict) -> dict
  update_user(id: str, data: dict) -> dict
  delete_user(id: str) -> None

Regole di business implementate:
  REQ-USR-B01 — unicità email case-insensitive
  REQ-USR-B02 — normalizzazione email in minuscolo
  REQ-USR-B03 — filtri lista per role e/o email
```

Dettaglio delle regole di business:

**REQ-USR-B01 — Unicità email**
- In `create_user`: `repo.email_exists(email.lower(), exclude_id=None)` → `EmailAlreadyExistsError` se True
- In `replace_user` e `update_user`: `repo.email_exists(email.lower(), exclude_id=id)` → 409 se un *altro* utente ha già quella email

**REQ-USR-B02 — Normalizzazione email**
- In ogni metodo che accetta `email` nel body: `data['email'] = data['email'].lower()` prima di `repo.save()`

**REQ-USR-B03 — Filtri lista**
- `list_users` passa `filters={'role': ..., 'email': ...}` a `repo.find_all(filters)`; il repository applica entrambi i filtri in AND logico
- Il campo `total` della risposta riflette il numero di utenti filtrati (non il totale assoluto)

---

### `app/repository.py` — Repository

Interfaccia comune a tutti e tre i backend:

```python
class UserRepository:
    def find_by_id(self, id: str) -> dict | None: ...
    def find_all(self, filters: dict) -> list[dict]: ...
    def save(self, user: dict) -> dict: ...     # insert se nuovo, update se esistente
    def delete(self, id: str) -> bool: ...
    def email_exists(self, email: str, exclude_id: str | None = None) -> bool: ...

def get_repository() -> UserRepository:
    backend = os.environ.get('STORAGE_BACKEND', 'memory').lower()
    if backend == 'json':   return JsonRepository()
    if backend == 'sqlite': return SqliteRepository()
    return MemoryRepository()               # fallback anche per valori non riconosciuti
```

---

## Data Models

### Risorsa `User`

| Campo | Tipo | Obbligatorio | Vincoli |
|---|---|---|---|
| `id` | `string (uuid)` | Sì (server-generated) | UUID v4, non accettato in input |
| `first_name` | `string` | Sì | `minLength: 1`, `maxLength: 50` |
| `last_name` | `string` | Sì | `minLength: 1`, `maxLength: 50` |
| `email` | `string (email)` | Sì | Formato email valido; salvato in lowercase; univoco case-insensitive |
| `company` | `string \| null` | No | `maxLength: 100` |
| `role` | `enum` | No (default `attendee`) | `attendee \| speaker \| organizer` |
| `created_at` | `string (date-time)` | Sì (server-generated) | ISO 8601 UTC, es. `2026-10-15T09:30:00Z` |
| `updated_at` | `string (date-time)` | Sì (server-generated) | ISO 8601 UTC |

### Schema `UserCreate` (input POST / PUT)

Campi accettati: `first_name`, `last_name`, `email`, `company` (opzionale), `role` (opzionale).  
Il campo `id` non viene accettato; se presente viene ignorato o rifiutato con 422.

### Schema `UserUpdate` (input PATCH)

Tutti i campi sono opzionali; viene aggiornato solo quanto fornito.

### Schema `UserPage` (output GET lista)

```json
{
  "items": [ /* array di User */ ],
  "page": 1,
  "page_size": 20,
  "total": 57
}
```

`total` riflette il numero totale di utenti che soddisfano i criteri di filtro attivi,
non il numero di elementi nella pagina corrente (REQ-USR-11.4).

### Schema SQLite

```sql
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    company     TEXT,
    role        TEXT NOT NULL DEFAULT 'attendee',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

Il vincolo `UNIQUE` su `email` garantisce l'unicità a livello di storage; la logica
applicativa (`email_exists`) lo verifica esplicitamente prima di raggiungere il DB.

---

## Correctness Properties

*Una property è una caratteristica o comportamento che deve essere verificabile su tutti i possibili input validi del sistema — essenzialmente una dichiarazione formale su ciò che il sistema deve fare. Le property costituiscono il ponte tra specifiche leggibili da umani e garanzie di correttezza verificabili automaticamente.*

Dopo il prework, le seguenti property sono state identificate come universalmente quantificabili e testate con property-based testing. Le property ridondanti (unicità email coperta da 3.10 e 9.1; normalizzazione coperta da 3.11 e 10.1) sono state consolidate.

---

### Property 1: Creazione preserva i dati di input

*Per qualsiasi* input valido di creazione utente (`first_name`, `last_name`, `email`, `role` valido o assente), la risorsa `User` restituita con stato 201 deve contenere esattamente i valori forniti (con `email` in minuscolo e `role` default `attendee` se assente), più un `id` in formato UUID v4 e `created_at`/`updated_at` in formato ISO 8601 UTC.

**Validates: Requirements 3.1, 3.2, 3.9**

---

### Property 2: Unicità email è invariante case-insensitive

*Per qualsiasi* email valida e qualsiasi variante di capitalizzazione della stessa stringa (es. `user@example.com`, `User@Example.COM`), tentare di creare un secondo utente con una variante dell'email già registrata deve sempre restituire 409 con codice `EMAIL_ALREADY_EXISTS`.

**Validates: Requirements 3.10, 9.1, 9.2**

---

### Property 3: Normalizzazione email è un'invariante di salvataggio

*Per qualsiasi* stringa email valida contenente caratteri maiuscoli, dopo la creazione o l'aggiornamento dell'utente, il campo `email` nella risposta deve essere in lettere minuscole.

**Validates: Requirements 3.11, 10.1, 10.2**

---

### Property 4: Filtro per ruolo è completo e preciso

*Per qualsiasi* insieme di utenti con ruoli misti e qualsiasi valore di `role` valido, la risposta di `GET /api/v1/users?role=<r>` deve contenere esclusivamente utenti il cui campo `role` è uguale a `<r>`, e il campo `total` deve corrispondere al numero di utenti filtrati.

**Validates: Requirements 4.6, 11.1, 11.4**

---

### Property 5: Filtro per email è completo e preciso (case-insensitive)

*Per qualsiasi* insieme di utenti e qualsiasi stringa email (con qualsiasi capitalizzazione), la risposta di `GET /api/v1/users?email=<e>` deve contenere esclusivamente utenti il cui campo `email` (in minuscolo) corrisponde a `<e>.lower()`, e `total` deve riflettere il conteggio filtrato.

**Validates: Requirements 4.7, 11.2, 11.4**

---

### Property 6: Filtri combinati applicano AND logico

*Per qualsiasi* insieme di utenti e qualsiasi combinazione di `role` e `email` forniti insieme, tutti gli utenti restituiti devono soddisfare **entrambi** i criteri contemporaneamente.

**Validates: Requirements 4.8, 11.3**

---

### Property 7: Round-trip GET dopo creazione

*Per qualsiasi* utente creato con successo, una successiva richiesta `GET /api/v1/users/{id}` deve restituire esattamente la stessa risorsa (tutti i campi uguali).

**Validates: Requirements 5.1, 5.3**

---

### Property 8: PUT sostituisce integralmente i campi scrivibili

*Per qualsiasi* utente esistente e qualsiasi body valido di sostituzione, dopo `PUT /api/v1/users/{id}` la risorsa restituita deve contenere i nuovi valori forniti; `id` e `created_at` devono restare invariati; `updated_at` deve essere aggiornato.

**Validates: Requirements 6.1, 6.6, 6.7**

---

### Property 9: PATCH aggiorna solo i campi presenti nel body

*Per qualsiasi* utente esistente e qualsiasi sottoinsieme non vuoto di campi validi inviati con PATCH, solo i campi inclusi nel body devono cambiare nella risorsa risultante; tutti gli altri campi devono restare identici al valore precedente.

**Validates: Requirements 7.1**

---

### Property 10: DELETE rende l'utente irrecuperabile

*Per qualsiasi* utente creato, dopo una `DELETE /api/v1/users/{id}` che restituisce 204, ogni successiva `GET /api/v1/users/{id}` deve restituire 404 con codice `NOT_FOUND`.

**Validates: Requirements 8.1, 8.2**

---

### Property 11: I tre backend producono risultati equivalenti

*Per qualsiasi* sequenza di operazioni CRUD (create, read, update, delete, list con filtri), i backend `memory`, `json` e `sqlite` devono restituire risultati logicamente equivalenti per gli stessi input.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

---

## Error Handling

### Gerarchia delle eccezioni e mappatura HTTP

```
app/exceptions.py
│
├── ValidationError(field, message)   → 422  { "code": "VALIDATION_ERROR" }
├── EmailAlreadyExistsError(message)  → 409  { "code": "EMAIL_ALREADY_EXISTS" }
└── NotFoundError(message)            → 404  { "code": "NOT_FOUND" }

Flask built-in:
└── BadRequest (da get_json silent=False) → 400  { "code": "MALFORMED_JSON" }
```

### Formato errore standard (REQ-USR-13.4)

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "Descrizione leggibile dell'errore",
    "details": {}
  }
}
```

### Gestione nel Router

```python
@bp.app_errorhandler(ValidationError)
def handle_validation(e):
    return jsonify({"error": {"code": "VALIDATION_ERROR",
                              "message": str(e), "details": {}}}), 422

@bp.app_errorhandler(EmailAlreadyExistsError)
def handle_conflict(e):
    return jsonify({"error": {"code": "EMAIL_ALREADY_EXISTS",
                              "message": str(e), "details": {}}}), 409

@bp.app_errorhandler(NotFoundError)
def handle_not_found(e):
    return jsonify({"error": {"code": "NOT_FOUND",
                              "message": str(e), "details": {}}}), 404

@bp.app_errorhandler(BadRequest)
def handle_bad_request(e):
    return jsonify({"error": {"code": "MALFORMED_JSON",
                              "message": "Corpo della richiesta non è JSON valido",
                              "details": {}}}), 400
```

### Tabella codici errore

| Situazione | Status | Codice errore |
|---|---|---|
| JSON malformato nel body | 400 | `MALFORMED_JSON` |
| Campo obbligatorio assente o fuori vincoli | 422 | `VALIDATION_ERROR` |
| Parametro query non valido (`role`, `page`, `page_size`) | 422 | `VALIDATION_ERROR` |
| Email duplicata (case-insensitive) | 409 | `EMAIL_ALREADY_EXISTS` |
| Utente non trovato per `id` | 404 | `NOT_FOUND` |

---

## Repository Implementations

### MemoryRepository

```
Struttura dati: dict Python  {id: user_dict}
Stato: in-memory, perso al riavvio del processo
Concorrenza: non thread-safe (accettabile per test/dev)

find_by_id(id)         → self._store.get(id)
find_all(filters)      → [u for u in self._store.values() se soddisfa filters]
save(user)             → self._store[user['id']] = user; return user
delete(id)             → self._store.pop(id, None); return id era presente
email_exists(email, exclude_id) → any(u['email']==email and u['id']!=exclude_id ...)
```

### JsonRepository

```
File: {DATA_DIR}/users.json
Formato: { "users": [ { user_dict }, ... ] }
Strategia: atomic read-modify-write (legge tutto, modifica in memoria, riscrive)

Ogni operazione:
  1. Apre e legge users.json (o parte da lista vuota se assente)
  2. Modifica la lista in memoria
  3. Riscrive atomicamente il file (write + rename)
```

Motivo della scelta atomic write: evita file corrotti in caso di crash a metà scrittura.

### SqliteRepository

```
File: {DATA_DIR}/users.db
Schema: tabella `users` (vedere sezione Data Models)
Libreria: solo stdlib sqlite3
Connessione: aperta e chiusa per ogni operazione (semplice, adeguato per il carico)

find_by_id(id)         → SELECT * FROM users WHERE id = ?
find_all(filters)      → SELECT * FROM users [WHERE role=? AND email=?]
save(user)             → INSERT OR REPLACE INTO users VALUES (...)
delete(id)             → DELETE FROM users WHERE id = ?; rows_affected > 0
email_exists(...)      → SELECT 1 FROM users WHERE email=? AND id != ? LIMIT 1
```

---

## Testing Strategy

### Approccio duale

Il testing usa due tipologie complementari:

1. **Unit test** — esempi specifici, casi limite, conformità al contratto per ogni endpoint
2. **Property-based test** — verifica delle 11 property universali con input generati automaticamente

Libreria PBT scelta: **Hypothesis** (Python). Ogni property test è configurato con
`@settings(max_examples=100)`.

---

### Unit Test — `services/user_service/tests/unit/`

#### `test_routes.py`

Per ogni endpoint viene verificato:
- Almeno 1 caso positivo (Happy Path)
- Principali casi di errore (400, 404, 409, 422)
- Almeno 1 chiamata `assert_matches_contract("user", method, path, response)` per endpoint
- Il service layer è mockato con `unittest.mock.patch`

```python
from contracts.validator import assert_matches_contract

def test_create_user_201(client, mock_service):
    mock_service.create_user.return_value = {...}  # user dict
    resp = client.post("/api/v1/users", json={...})
    assert resp.status_code == 201
    assert_matches_contract("user", "POST", "/api/v1/users", resp)

def test_create_user_409_duplicate_email(client, mock_service):
    mock_service.create_user.side_effect = EmailAlreadyExistsError("...")
    resp = client.post("/api/v1/users", json={...})
    assert resp.status_code == 409
    assert_matches_contract("user", "POST", "/api/v1/users", resp)
```

Endpoint coperti: `GET /health`, `POST`, `GET` (lista), `GET` (singolo), `PUT`, `PATCH`, `DELETE`.

#### `test_service.py`

Verifica ogni regola `REQ-USR-B*` in isolamento con repository mockato:

```python
# REQ-USR-B01 — Unicità email
def test_create_raises_email_exists_when_duplicate():
    repo = MagicMock()
    repo.email_exists.return_value = True
    svc = UserService(repo)
    with pytest.raises(EmailAlreadyExistsError):
        svc.create_user({"first_name": "A", "last_name": "B", "email": "a@b.com"})

# REQ-USR-B02 — Normalizzazione email
def test_create_normalizes_email_to_lowercase():
    repo = MagicMock()
    repo.email_exists.return_value = False
    repo.save.side_effect = lambda u: u
    svc = UserService(repo)
    result = svc.create_user({"first_name": "A", "last_name": "B", "email": "USER@EXAMPLE.COM"})
    assert result["email"] == "user@example.com"

# REQ-USR-B03 — Filtri lista
def test_list_applies_role_filter():
    repo = MagicMock()
    repo.find_all.return_value = [{"role": "speaker", ...}]
    svc = UserService(repo)
    result = svc.list_users({"role": "speaker"}, page=1, page_size=20)
    repo.find_all.assert_called_with({"role": "speaker"})
```

#### `test_repository.py`

Test CRUD completo parametrizzato sui tre backend:

```python
@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", request.param)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return get_repository()

def test_save_and_find_by_id(repo):
    user = make_user()
    repo.save(user)
    found = repo.find_by_id(user["id"])
    assert found == user

def test_email_exists_case_insensitive(repo):
    user = make_user(email="user@example.com")
    repo.save(user)
    assert repo.email_exists("USER@EXAMPLE.COM", exclude_id=None) is True

def test_delete_removes_user(repo):
    user = make_user()
    repo.save(user)
    repo.delete(user["id"])
    assert repo.find_by_id(user["id"]) is None
```

---

### Property-Based Test — con Hypothesis

Ogni property usa `@settings(max_examples=100)` e un tag di riferimento al design.

```python
# Feature: user-service, Property 3: normalizzazione email invariante
@given(email=emails())
@settings(max_examples=100)
def test_email_always_stored_lowercase(email):
    """Feature: user-service, Property 3: normalizzazione email invariante"""
    svc = UserService(MemoryRepository())
    result = svc.create_user({"first_name": "A", "last_name": "B", "email": email})
    assert result["email"] == email.lower()

# Feature: user-service, Property 2: unicità email case-insensitive
@given(email=emails())
@settings(max_examples=100)
def test_duplicate_email_always_rejected(email):
    """Feature: user-service, Property 2: unicità email case-insensitive"""
    svc = UserService(MemoryRepository())
    svc.create_user({"first_name": "A", "last_name": "B", "email": email.lower()})
    with pytest.raises(EmailAlreadyExistsError):
        svc.create_user({"first_name": "C", "last_name": "D", "email": email.upper()})
```

Tag format: **Feature: user-service, Property {N}: {testo property}**

Ogni property del documento Design corrisponde a esattamente 1 test property-based.

---

### Comandi

```bash
# Unit test con coverage
cd services/user_service
pytest tests/unit --cov=app --cov-report=term-missing

# Solo property-based test
pytest tests/unit/test_properties.py -v

# Tutti i test
pytest tests/ -v
```

Obiettivo coverage: ≥ 80% del package `app`.

---

## Contract Reference

Il contratto definitivo è `contracts/openapi/user-service.yaml` (non modificabile).

Tutti i test del router devono includere almeno una chiamata `assert_matches_contract`
per endpoint, importando il validator dal path relativo al root del progetto:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
from contracts.validator import assert_matches_contract
```

### Endpoint dichiarati nel contratto

| Metodo | Path | Status possibili |
|---|---|---|
| `GET` | `/health` | 200 |
| `POST` | `/api/v1/users` | 201, 400, 409, 422 |
| `GET` | `/api/v1/users` | 200, 422 |
| `GET` | `/api/v1/users/{id}` | 200, 404 |
| `PUT` | `/api/v1/users/{id}` | 200, 404, 409, 422 |
| `PATCH` | `/api/v1/users/{id}` | 200, 404, 409, 422 |
| `DELETE` | `/api/v1/users/{id}` | 204, 404 |

Ogni risposta restituita dal servizio deve superare la validazione dello schema
`Draft7Validator` applicata dal validator sugli schemi del contratto.
