# Design Document — event-service

## Overview

L'**event-service** è il microservizio che gestisce le conferenze (Event) della
piattaforma TechConf e il loro ciclo di vita. Espone un'API REST sotto il base path
`/api/v1/events` e, a differenza dello `user-service`, **dipende** da un altro
servizio: per ogni operazione che tocca `organizer_id` interroga lo `user-service`
via HTTP per verificare che l'organizzatore esista (REQ-EVT-B01) e abbia il ruolo
`organizer` (REQ-EVT-B02).

Porta di ascolto: `PORT` (default `5002` in sviluppo).
Base path: `/api/v1/events`.
Contratto definitivo (fonte di verità, non modificabile): `contracts/openapi/event-service.yaml`.
URL della dipendenza: `USER_SERVICE_URL` (default `http://localhost:5001`) — letto
**esclusivamente** dalla configurazione, mai hard-coded.

Requisiti coperti: REQ-EVT-1 … REQ-EVT-17, con le regole di business
`REQ-EVT-B01` … `REQ-EVT-B06`.

Il design segue la **stessa impostazione architetturale** dello `user-service`
(tre livelli Router → Service → Repository), coerente con `structure.md`, con
l'aggiunta di un **client HTTP dedicato** (`UserServiceClient`) come unico punto di
comunicazione verso lo `user-service`.

---

## Architecture

Il servizio è strutturato in **tre livelli nettamente separati** più un **client
esterno** verso lo `user-service`:

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Client                          │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP Request
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Router  (routes.py)                       │
│  • Parsing body JSON  → 400 MALFORMED_JSON                  │
│  • Validazione tipi/formati HTTP di base                    │
│  • Costruzione risposta (status code, header Location)      │
│  • Mappatura eccezioni → JSON error (app_errorhandler)      │
│  • NESSUNA regola di business REQ-EVT-B*                    │
└────────────────────────────┬────────────────────────────────┘
                             │ chiama metodi Python
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Service Layer  (service.py)                 │
│  • Implementa TUTTE le regole REQ-EVT-B01..B06             │
│  • Validazione campi Event, coerenza date, transizioni      │
│  • Generazione UUID v4, timestamp ISO 8601 UTC              │
│  • Normalizzazione price (2 decimali)                       │
│  • Non conosce Flask, non costruisce Response               │
│  • Riceve repo e user_client per dependency injection       │
└──────────────┬──────────────────────────────┬───────────────┘
               │ repo (CRUD)                   │ user_client (HTTP)
               ▼                               ▼
┌───────────────────────────────┐  ┌────────────────────────────────┐
│      Repository                │  │   UserServiceClient            │
│      (repository.py)           │  │   (user_client.py)             │
│  • Unico punto che conosce     │  │  • Unico punto che parla con   │
│    STORAGE_BACKEND             │  │    user-service via HTTP       │
│  ┌────────┐┌───────┐┌────────┐ │  │  • GET {USER_SERVICE_URL}/...  │
│  │Memory  ││Json   ││Sqlite  │ │  │  • timeout esatto 2s (B05)     │
│  │Repo    ││Repo   ││Repo    │ │  │  • mappa errori → eccezioni    │
│  └────────┘└───────┘└────────┘ │  └───────────────┬────────────────┘
└───────────────────────────────┘                  │ HTTP (requests)
                                                    ▼
                                     ┌────────────────────────────────┐
                                     │   user-service (esterno)       │
                                     │   GET /api/v1/users/{id}       │
                                     └────────────────────────────────┘
```

### Flusso di una richiesta tipo — `POST /api/v1/events`

Il flusso mostra la biforcazione 201 / 422 / 503 introdotta dalla dipendenza esterna
(REQ-EVT-B01, REQ-EVT-B02, REQ-EVT-B05):

```
Client
  │ POST /api/v1/events  {title, organizer_id, venue, city,
  │                       start_date, end_date, capacity, price, [status]}
  ▼
routes.py
  ├── request.get_json(silent=False)          → 400 MALFORMED_JSON  (REQ-EVT-4.5)
  └── chiama service.create_event(data)
        ▼
      service.py
        ├── validazione locale campi/schema    → 422 VALIDATION_ERROR (REQ-EVT-3.*)
        │     (title, description, venue, city, capacity, price 2 dec,
        │      no campi read-only, no campi sconosciuti)
        ├── coerenza date end_date >= start_date→ 422 VALIDATION_ERROR (REQ-EVT-B03)
        │
        ├── user_client.validate_organizer(organizer_id)   [REQ-EVT-B01/B02]
        │     ├── GET {USER_SERVICE_URL}/api/v1/users/{organizer_id}  (timeout 2s)
        │     │
        │     ├── 404 user-service ─────────────→ 422 REFERENCE_NOT_FOUND (B01)
        │     ├── role != 'organizer' ──────────→ 422 INVALID_ORGANIZER  (B02)
        │     ├── timeout / conn refused / 5xx ─→ 503 DEPENDENCY_UNAVAILABLE (B05)
        │     └── 200 & role == 'organizer' ────→ OK, prosegue
        │
        ├── status assente → 'draft'            (REQ-EVT-4.2)
        ├── genera id uuid4(), created_at, updated_at (utc_now_iso())
        └── repo.save(event_dict)
              ▼
            repository.py (backend attivo)
              └── inserisce → restituisce event_dict
        ▲
      service.py restituisce event_dict
  ▲
routes.py
  ├── costruisce risposta 201
  ├── imposta header Location: /api/v1/events/{id}   (REQ-EVT-4.3)
  └── return jsonify(event_dict), 201
```

---

## Components and Interfaces

### `app/__init__.py` — Factory

```python
def create_app(repo=None, user_client=None) -> Flask:
    app = Flask(__name__)
    if repo is None:
        repo = get_repository()                     # da config STORAGE_BACKEND
    if user_client is None:
        from .config import USER_SERVICE_URL
        user_client = UserServiceClient(USER_SERVICE_URL)  # timeout default 2s
    from .routes import bp
    bp.repo = repo                # dependency injection
    bp.user_client = user_client  # dependency injection
    app.register_blueprint(bp)
    _register_error_handlers(app)
    return app
```

La factory accetta `repo` e `user_client` opzionali: nei test si iniettano un
`MemoryRepository` e un `user_client` mockato, così da testare il router senza rete.

---

### `app/config.py` — Configurazione

Unico punto che legge `os.environ`; nessun'altra parte del codice accede direttamente
alle variabili d'ambiente (REQ-EVT-1.8).

| Variabile | Default | Uso | Requisito |
|---|---|---|---|
| `PORT` | `5002` | Porta Flask | REQ-EVT-1.1, 1.2 |
| `USER_SERVICE_URL` | `http://localhost:5001` | URL base user-service | REQ-EVT-1.3, 1.4 |
| `STORAGE_BACKEND` | `memory` | Backend persistenza (`memory`/`json`/`sqlite`) | REQ-EVT-1.5, 1.7 |
| `DATA_DIR` | `./data` | Directory file json/sqlite | REQ-EVT-1.6 |

```python
import os

PORT             = int(os.environ.get("PORT", 5002))
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
STORAGE_BACKEND  = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR         = os.environ.get("DATA_DIR", "./data")
```

Il fallback di `STORAGE_BACKEND` a `memory` per valori non riconosciuti (REQ-EVT-1.7)
è realizzato in `get_repository()` (vedi Repository), non qui: `config` espone il
valore grezzo, la factory del repository decide il fallback.

---

### `app/models.py` — Modello dati

```python
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

EVENT_STATUSES = ("draft", "published", "cancelled")
DEFAULT_STATUS = "draft"

# REQ-EVT-B04 — transizioni ammesse (coppie stato_corrente → stato_nuovo)
ALLOWED_TRANSITIONS = {
    ("draft", "published"),
    ("draft", "cancelled"),
    ("published", "cancelled"),
}

def utc_now_iso() -> str:
    """Timestamp corrente in ISO 8601 UTC: 2026-10-15T09:30:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

@dataclass
class Event:
    id: str
    title: str
    organizer_id: str
    venue: str
    city: str
    start_date: str          # YYYY-MM-DD
    end_date: str            # YYYY-MM-DD
    capacity: int
    price: float             # >= 0, 2 decimali
    status: str              # draft | published | cancelled
    created_at: str          # ISO 8601 UTC
    updated_at: str          # ISO 8601 UTC
    description: Optional[str] = None   # nullable, SEMPRE presente nell'output

    def to_dict(self) -> dict:
        # description è sempre presente (anche se None) per conformità al
        # contratto (schema Event) — REQ-EVT-6.3, 17.6.
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "organizer_id": self.organizer_id,
            "venue": self.venue,
            "city": self.city,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "capacity": self.capacity,
            "price": round(self.price, 2),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
```

Nota su `price`: il valore viene sempre normalizzato a due cifre decimali in output
(REQ-EVT-3.11, 17.4). La rappresentazione numerica JSON conserva il valore; il
validator del contratto ammette un `number` non negativo.

---

### `app/exceptions.py` — Eccezioni custom

```python
class ValidationError(Exception):
    """→ 422 VALIDATION_ERROR"""
    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)

class NotFoundError(Exception):
    """→ 404 NOT_FOUND (risorsa Event inesistente)"""

class ReferenceNotFoundError(Exception):
    """→ 422 REFERENCE_NOT_FOUND (organizer inesistente in user-service) — B01"""

class InvalidOrganizerError(Exception):
    """→ 422 INVALID_ORGANIZER (utente esiste ma role != organizer) — B02"""

class InvalidStatusTransitionError(Exception):
    """→ 422 INVALID_STATUS_TRANSITION (transizione non ammessa) — B04"""

class DependencyUnavailableError(Exception):
    """→ 503 DEPENDENCY_UNAVAILABLE (user-service irraggiungibile) — B05"""
```

---

### `app/user_client.py` — Client HTTP verso user-service

Questo componente è **l'unico punto** che comunica con lo `user-service`. L'URL base
proviene **esclusivamente** da `USER_SERVICE_URL` tramite `config` e non è mai
hard-coded (requisito vincolante: un URL hard-coded è penalizzante in sede d'esame,
REQ-EVT-1.4 e Platform Standards).

```python
import requests
from .exceptions import (
    ReferenceNotFoundError,
    InvalidOrganizerError,
    DependencyUnavailableError,
)

class UserServiceClient:
    def __init__(self, base_url: str, timeout: float = 2.0):
        # base_url proviene SOLO da USER_SERVICE_URL (config), mai hard-coded.
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout          # REQ-EVT-B05: timeout ESATTO 2 secondi

    def get_user(self, user_id: str) -> dict:
        """GET {base_url}/api/v1/users/{user_id}.

        Mappatura risposte/errori:
          200          → restituisce il dict utente (contiene 'role')
          404          → ReferenceNotFoundError  (→ 422 REFERENCE_NOT_FOUND)  [B01]
          5xx          → DependencyUnavailableError (→ 503)                   [B05]
          Timeout      → DependencyUnavailableError (→ 503)                   [B05]
          ConnError    → DependencyUnavailableError (→ 503)                   [B05]
          altri 4xx    → DependencyUnavailableError (→ 503)  (vedi nota)      [B05]
        """
        url = f"{self._base_url}/api/v1/users/{user_id}"
        try:
            resp = requests.get(url, timeout=self._timeout)
        except requests.exceptions.Timeout:
            raise DependencyUnavailableError("user-service timeout")        # B05
        except requests.exceptions.ConnectionError:
            raise DependencyUnavailableError("user-service unreachable")    # B05

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise ReferenceNotFoundError(f"organizer {user_id} not found")  # B01
        if 500 <= resp.status_code < 600:
            raise DependencyUnavailableError("user-service 5xx")            # B05
        # Stati inattesi (4xx diversi da 404): la dipendenza non si comporta
        # secondo contratto, quindi la trattiamo come non attendibile → 503,
        # coerentemente con B05 (meglio segnalare indisponibilità che dedurre
        # un esito di business da una risposta non prevista).
        raise DependencyUnavailableError(
            f"unexpected user-service status {resp.status_code}"
        )

    def validate_organizer(self, user_id: str) -> dict:
        """Usato dal service layer: verifica esistenza (B01) e ruolo (B02)."""
        user = self.get_user(user_id)                 # può sollevare Reference/Dependency
        if user.get("role") != "organizer":           # B02
            raise InvalidOrganizerError(
                f"user {user_id} is not an organizer"
            )
        return user
```

Diagramma della mappatura eccezioni del client:

```
                        get_user(user_id)
                              │
        ┌─────────────────────┼───────────────────────────┐
        │                     │                            │
   requests OK           Timeout/ConnError            (nessuna)
        │                     │
   status?            DependencyUnavailableError (503) [B05]
        │
  ┌─────┼───────────────┬──────────────┐
 200   404            5xx           altri 4xx
  │     │               │               │
 dict  Reference    Dependency      Dependency
       NotFound     Unavailable     Unavailable
       (422 B01)    (503 B05)       (503 B05, nota)
```

---

### `app/service.py` — Service Layer

```
EventService(repo: EventRepository, user_client: UserServiceClient)

Metodi pubblici:
  create_event(data: dict) -> dict
  list_events(filters: dict, page: int, page_size: int) -> dict
  get_event(id: str) -> dict
  replace_event(id: str, data: dict) -> dict
  update_event(id: str, data: dict) -> dict
  delete_event(id: str) -> None
```

Regole di business implementate (tutte e sole nel service layer):

**REQ-EVT-B01 / B02 — Esistenza e ruolo dell'organizzatore**
- `create_event`: dopo la validazione locale, chiama **sempre**
  `user_client.validate_organizer(data["organizer_id"])`.
- `replace_event` (PUT): `organizer_id` è obbligatorio; valida **sempre**
  l'organizzatore (REQ-EVT-7.6, 10.3).
- `update_event` (PATCH): valida l'organizzatore **solo se** `organizer_id` è presente
  nel body **e diverso** dal valore corrente (REQ-EVT-8.5, 8.6, 8.7, 10.4). Se assente
  o uguale, **non** chiama user-service.
- `validate_organizer` solleva `ReferenceNotFoundError` (→422 REFERENCE_NOT_FOUND) se
  l'utente non esiste, `InvalidOrganizerError` (→422 INVALID_ORGANIZER) se `role` ≠
  `organizer`, `DependencyUnavailableError` (→503) se la dipendenza è indisponibile.

**REQ-EVT-B03 — Coerenza delle date**
- Regola: `end_date >= start_date` (confronto lessicografico su `YYYY-MM-DD`, che è
  equivalente al confronto cronologico). In caso contrario → `ValidationError`
  (422 VALIDATION_ERROR).
- Su PATCH la regola si applica alla **coppia risultante** dopo il merge dei campi
  presenti nel body con quelli correnti (REQ-EVT-12.3).

**REQ-EVT-B04 — Transizioni del ciclo di vita**
- `ALLOWED_TRANSITIONS = {(draft→published), (draft→cancelled), (published→cancelled)}`.
- Se lo `status` richiesto è **uguale** a quello corrente → aggiornamento idempotente,
  **nessuna** transizione (REQ-EVT-13.5).
- Se `status` cambia e la coppia `(corrente, nuovo)` non è in `ALLOWED_TRANSITIONS`
  → `InvalidStatusTransitionError` (422 INVALID_STATUS_TRANSITION).
- La regola si applica quando `status` è presente e diverso in PUT/PATCH.

**REQ-EVT-B05 — Indisponibilità di user-service**
- Ogni fallimento della dipendenza (timeout 2s esatto, connessione rifiutata/host non
  raggiungibile, `5xx`) → 503 DEPENDENCY_UNAVAILABLE. La logica di mapping vive nel
  `UserServiceClient`; il service la propaga senza convertirla in un esito di business.

**REQ-EVT-B06 — Filtri di lista**
- `list_events` applica il filtro `status` (uguaglianza esatta con Event_Status) e il
  filtro `city` (**Confronto_Città**: uguaglianza esatta case-insensitive, senza
  corrispondenze parziali) in **AND logico**.
- `total` è calcolato **dopo** i filtri e **prima** della paginazione
  (REQ-EVT-15.4); `items` è la pagina estratta dall'insieme filtrato (REQ-EVT-15.5).

**Campi generati / read-only**
- `id` (UUID v4) e `created_at` sono generati alla creazione e **mai** modificati
  (REQ-EVT-7.2, 8.2). `updated_at` è impostato al timestamp corrente ad ogni modifica
  (REQ-EVT-7.3, 8.3). `price` è normalizzato a 2 decimali (REQ-EVT-3.11, 17.4).

Dettaglio dei metodi di modifica:

| Metodo | description omessa | status omesso | validazione organizer |
|---|---|---|---|
| `create_event` | `null` (REQ-EVT-3.3) | `draft` (REQ-EVT-4.2) | sempre (B01/B02) |
| `replace_event` (PUT) | `null` (REQ-EVT-7.4) | mantiene corrente (REQ-EVT-7.5) | sempre (REQ-EVT-7.6) |
| `update_event` (PATCH) | invariato se assente (REQ-EVT-8.4) | invariato se assente | solo se presente e diverso (REQ-EVT-8.5-8.7) |

---

### `app/repository.py` — Repository

Interfaccia comune ai tre backend (identica per contratto a quella dello user-service,
adattata a Event):

```python
class EventRepository:
    def find_by_id(self, id: str) -> dict | None: ...
    def find_all(self, filters: dict) -> list[dict]: ...   # applica status/city (B06)
    def save(self, event: dict) -> dict: ...               # insert se nuovo, update se esistente
    def delete(self, id: str) -> bool: ...                 # True se esisteva

def get_repository() -> EventRepository:
    from .config import STORAGE_BACKEND, DATA_DIR
    backend = (STORAGE_BACKEND or "memory").lower()
    if backend == "json":   return JsonRepository(DATA_DIR)
    if backend == "sqlite": return SqliteRepository(DATA_DIR)
    return MemoryRepository()          # fallback anche per valori non riconosciuti (REQ-EVT-1.7)
```

Il filtro `city` case-insensitive esatto e il filtro `status` (AND logico) possono
essere applicati o nel repository (`find_all(filters)`) o nel service dopo un
`find_all({})`. Per coerenza con lo user-service e per mantenere il repository
"stupido", **il service applica i filtri, il conteggio `total` e la paginazione**;
`find_all` restituisce l'insieme completo o pre-filtrato in modo equivalente tra i
backend. In entrambi i casi la semantica osservabile (REQ-EVT-B06) è identica.

---

## Data Models

### Risorsa `Event`

| Campo | Tipo | Obbligatorio (input) | Vincoli | Requisito |
|---|---|---|---|---|
| `id` | `string (uuid)` | No (server-generated) | UUID v4, non accettato in input | 3.14, 3.15 |
| `title` | `string` | Sì | `minLength: 3`, `maxLength: 120` | 3.2 |
| `description` | `string \| null` | No | `maxLength: 2000`; default `null`; sempre presente in output | 3.3, 3.4 |
| `organizer_id` | `string (uuid)` | Sì | formato UUID; validato via user-service | 3.5, B01 |
| `venue` | `string` | Sì | `maxLength: 100` | 3.6 |
| `city` | `string` | Sì | `maxLength: 60` | 3.7 |
| `start_date` | `string (date)` | Sì | `YYYY-MM-DD` valida | 3.8 |
| `end_date` | `string (date)` | Sì | `YYYY-MM-DD` valida; `>= start_date` | 3.8, B03 |
| `capacity` | `integer` | Sì | `1 <= capacity <= 10000` | 3.9 |
| `price` | `number` | Sì | `>= 0.00`, max 2 decimali (EUR) | 3.10, 3.11, 17.4 |
| `status` | `enum` | No (default `draft`) | `draft \| published \| cancelled` | 3.12, 4.2 |
| `created_at` | `string (date-time)` | No (server-generated) | ISO 8601 UTC | 3.15, 17.3 |
| `updated_at` | `string (date-time)` | No (server-generated) | ISO 8601 UTC | 3.15, 17.3 |

Campi read-only (rifiutati in input con 422, REQ-EVT-3.14): `id`, `created_at`,
`updated_at`. Qualsiasi campo non definito dallo schema → 422 (REQ-EVT-3.13,
`additionalProperties: false`).

### Schema `EventCreate` (input POST / PUT)

Campi obbligatori: `title`, `organizer_id`, `venue`, `city`, `start_date`,
`end_date`, `capacity`, `price`. Campi opzionali: `description`, `status`.
`additionalProperties: false`.

### Schema `EventUpdate` (input PATCH)

Tutti i campi opzionali; si aggiornano solo quelli forniti. `additionalProperties: false`.

### Schema `EventPage` (output GET lista)

```json
{
  "items": [ /* array di Event */ ],
  "page": 1,
  "page_size": 20,
  "total": 57
}
```

`total` = numero di Event che soddisfano i filtri attivi, calcolato **prima** della
paginazione (REQ-EVT-15.4).

### Schema SQLite

```sql
CREATE TABLE IF NOT EXISTS events (
    id            TEXT    PRIMARY KEY,
    title         TEXT    NOT NULL,
    description   TEXT,                    -- nullable
    organizer_id  TEXT    NOT NULL,
    venue         TEXT    NOT NULL,
    city          TEXT    NOT NULL,
    start_date    TEXT    NOT NULL,        -- YYYY-MM-DD
    end_date      TEXT    NOT NULL,        -- YYYY-MM-DD
    capacity      INTEGER NOT NULL,
    price         TEXT    NOT NULL,        -- vedi nota
    status        TEXT    NOT NULL DEFAULT 'draft',
    created_at    TEXT    NOT NULL,        -- ISO 8601 UTC
    updated_at    TEXT    NOT NULL
);
```

**Nota su `price`**: per evitare gli errori di arrotondamento del tipo `REAL`
(floating point binario), `price` viene memorizzato come **stringa** con due decimali
(es. `"149.00"`) e riconvertito in `float`/`number` al momento della lettura,
restituendolo sempre con `round(value, 2)` (REQ-EVT-17.4). In alternativa si può usare
`NUMERIC`, ma la stringa garantisce la precisione a due decimali in modo deterministico
tra i tre backend.

### Schema file JSON

```json
{ "events": [ { /* event_dict */ }, ... ] }
```

Strategia atomic read-modify-write (leggi tutto, modifica in memoria, riscrivi con
write+rename) per evitare file corrotti in caso di crash a metà scrittura.

---

## Correctness Properties

*Una property è una caratteristica o comportamento che deve essere verificabile su
tutti i possibili input validi del sistema — essenzialmente una dichiarazione formale
su ciò che il sistema deve fare. Le property costituiscono il ponte tra specifiche
leggibili da umani e garanzie di correttezza verificabili automaticamente.*

Dopo il prework, le seguenti property sono state identificate come universalmente
quantificabili e verranno testate con property-based testing (Hypothesis). Le property
di validazione dei singoli campi (REQ-EVT-3.*) sono consolidate in una property di
validazione più due property mirate (price a 2 decimali, rifiuto campi read-only/
sconosciuti). La conformità al contratto (17.6, 17.7) è verificata trasversalmente via
`assert_matches_contract` nei test del router.

### Property 1: La creazione preserva l'input e applica i default

*Per qualsiasi* body di creazione valido (tutti i Campi_obbligatori nei rispettivi
vincoli) con un organizzatore valido, la risorsa `Event` restituita con stato 201 deve
contenere esattamente i valori scrivibili forniti, con `status` uguale a `draft` se
assente, `description` uguale a `null` se assente, un `id` in formato UUID v4 e
`created_at`/`updated_at` in formato ISO 8601 UTC.

**Validates: Requirements 3.3, 3.15, 4.1, 4.2, 4.4**

### Property 2: L'input non valido viene sempre rifiutato con 422

*Per qualsiasi* body che viola almeno un vincolo di schema (campo obbligatorio
mancante, `title` fuori range, `capacity` fuori range, `venue`/`city`/`description`
oltre la lunghezza massima, `organizer_id` non UUID, `status` non ammesso, data non
valida), l'Event_Service deve rispondere con stato 422 e Error_Response con codice
`VALIDATION_ERROR`.

**Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.12, 4.6, 17.8**

### Property 3: I campi read-only e i campi sconosciuti sono sempre rifiutati

*Per qualsiasi* body POST/PUT/PATCH che include un Campo_read_only (`id`,
`created_at`, `updated_at`) o un campo non definito dallo schema applicabile,
l'Event_Service deve rispondere con stato 422 e codice `VALIDATION_ERROR`.

**Validates: Requirements 3.13, 3.14**

### Property 4: `price` è sempre non negativo con due decimali

*Per qualsiasi* `price` di input valido, l'Event restituito deve rappresentare `price`
come numero maggiore o uguale a 0 con esattamente due cifre decimali; *per qualsiasi*
`price` negativo o con più di due decimali, l'Event_Service deve rispondere con 422 e
codice `VALIDATION_ERROR`.

**Validates: Requirements 3.10, 3.11, 17.4**

### Property 5: Organizzatore inesistente produce sempre 422 REFERENCE_NOT_FOUND

*Per qualsiasi* body altrimenti valido, se lo user-service risponde 404 per
`organizer_id`, l'operazione (POST, PUT, o PATCH che cambia organizzatore) deve essere
interrotta con stato 422 e codice `REFERENCE_NOT_FOUND`.

**Validates: Requirements 10.2, 10.3, 10.4, 10.5**

### Property 6: Organizzatore con ruolo errato produce sempre 422 INVALID_ORGANIZER

*Per qualsiasi* utente restituito dallo user-service con `role` diverso da `organizer`
o privo del campo `role`, l'operazione deve essere interrotta con stato 422 e codice
`INVALID_ORGANIZER`; *per qualsiasi* utente con `role` uguale a `organizer` la
validazione del ruolo deve considerarsi soddisfatta.

**Validates: Requirements 11.1, 11.2**

### Property 7: La coerenza delle date è un invariante

*Per qualsiasi* coppia di date valide, l'Event_Service accetta l'operazione se e solo
se `end_date >= start_date`; se `end_date < start_date` deve rispondere con 422 e
codice `VALIDATION_ERROR`. Su PATCH la regola si applica alla coppia risultante dal
merge dei campi.

**Validates: Requirements 12.1, 12.2, 12.3**

### Property 8: Solo le transizioni ammesse sono accettate

*Per qualsiasi* coppia (stato_corrente, stato_richiesto), l'Event_Service accetta il
cambiamento se e solo se la coppia appartiene a `ALLOWED_TRANSITIONS`
{draft→published, draft→cancelled, published→cancelled} oppure i due stati sono uguali
(aggiornamento idempotente); ogni altra coppia deve produrre 422 con codice
`INVALID_STATUS_TRANSITION`.

**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5**

### Property 9: Il fallimento della dipendenza produce sempre 503

*Per qualsiasi* modalità di fallimento dello user-service (timeout oltre 2 secondi,
connessione rifiutata/host non raggiungibile, risposta `5xx`), quando è richiesta la
validazione dell'organizzatore l'Event_Service deve rispondere con stato 503 e codice
`DEPENDENCY_UNAVAILABLE`.

**Validates: Requirements 14.1, 14.2, 14.3, 14.4**

### Property 10: I filtri di lista sono completi, precisi e con `total` corretto

*Per qualsiasi* insieme di Event e qualsiasi combinazione dei filtri `status` e `city`,
la lista restituita deve contenere esclusivamente Event che soddisfano tutti i filtri
forniti in AND logico (`city` confrontata in modo esatto case-insensitive), e `total`
deve essere uguale al numero di Event filtrati calcolato prima della paginazione.

**Validates: Requirements 15.1, 15.2, 15.3, 15.4, 5.1, 5.8**

### Property 11: La paginazione rispetta i suoi invarianti

*Per qualsiasi* insieme di Event e qualsiasi coppia valida `(page, page_size)`, la
risposta deve avere `len(items) <= page_size`, i campi `page` e `page_size` uguali ai
valori effettivi applicati (default 1 e 20 se assenti), e `items` uguale al segmento di
pagina dell'insieme filtrato.

**Validates: Requirements 5.1, 5.2, 5.3, 5.9, 15.5**

### Property 12: Round-trip GET dopo creazione

*Per qualsiasi* Event creato con successo, una successiva `GET /api/v1/events/{id}`
deve restituire stato 200 e una risorsa con tutti i campi uguali a quella creata;
*per qualsiasi* `id` non associato ad alcun Event, la GET deve restituire 404 con
codice `NOT_FOUND`.

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 13: PATCH aggiorna solo i campi presenti nel body

*Per qualsiasi* Event esistente e qualsiasi sottoinsieme non vuoto di campi scrivibili
validi inviati con PATCH, nella risorsa risultante devono cambiare esclusivamente i
campi inclusi nel body (più `updated_at`); tutti gli altri campi, incluso `id` e
`created_at`, devono restare identici al valore precedente.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 14: PUT sostituisce i campi scrivibili preservando id/created_at

*Per qualsiasi* Event esistente e qualsiasi body di sostituzione valido, dopo
`PUT /api/v1/events/{id}` la risorsa deve contenere i nuovi valori forniti,
`description` uguale a `null` se omessa, lo `status` corrente se omesso, `id` e
`created_at` invariati e `updated_at` aggiornato.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

### Property 15: DELETE rende l'Event irraggiungibile

*Per qualsiasi* Event creato, dopo una `DELETE /api/v1/events/{id}` che restituisce
204, ogni successiva `GET /api/v1/events/{id}` deve restituire 404 con codice
`NOT_FOUND`; una DELETE su un `id` inesistente deve restituire 404.

**Validates: Requirements 9.1, 9.2**

### Property 16: I tre backend producono risultati equivalenti

*Per qualsiasi* sequenza di operazioni (create, read, update, replace, delete, list con
filtri), i backend `memory`, `json` e `sqlite` devono restituire risultati logicamente
equivalenti a partire dagli stessi input.

**Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5**

---

## Error Handling

### Tabella completa situazione → status → codice

| Situazione | Status | Codice errore | Requisito |
|---|---|---|---|
| JSON malformato nel body | 400 | `MALFORMED_JSON` | 4.5, 7.8, 8.9 |
| Campo obbligatorio assente / fuori vincoli / campo read-only o sconosciuto | 422 | `VALIDATION_ERROR` | 3.1-3.14, 17.8 |
| Parametro query non valido (`page`, `page_size`, `status`, `city`) | 422 | `VALIDATION_ERROR` | 5.4-5.7 |
| `end_date < start_date` | 422 | `VALIDATION_ERROR` | B03 (12.2) |
| Organizzatore inesistente (404 da user-service) | 422 | `REFERENCE_NOT_FOUND` | B01 (10.5) |
| Utente esiste ma `role` ≠ `organizer` | 422 | `INVALID_ORGANIZER` | B02 (11.2) |
| Transizione di stato non ammessa | 422 | `INVALID_STATUS_TRANSITION` | B04 (13.4) |
| Event inesistente per `id` | 404 | `NOT_FOUND` | 6.2, 7.7, 8.8, 9.2, 17.9 |
| user-service in timeout / conn refused / 5xx | 503 | `DEPENDENCY_UNAVAILABLE` | B05 (14.*) |

### Distinzione tra i due 404

È fondamentale non confondere i due casi che coinvolgono lo stato 404:

- **404 sulla risorsa Event** (l'`id` nel path non corrisponde ad alcun Event
  memorizzato) → l'Event_Service risponde **404 NOT_FOUND** (REQ-EVT-6.2, 9.2).
- **404 restituito dallo user-service** durante la validazione dell'organizzatore
  (l'`organizer_id` non esiste) → l'Event_Service **non propaga 404**, ma lo traduce in
  **422 REFERENCE_NOT_FOUND** (REQ-EVT-B01), perché dal punto di vista del client
  dell'event-service si tratta di un riferimento non valido nel body, non di una
  risorsa Event mancante.

### Error handler Flask (livello app)

```python
from werkzeug.exceptions import BadRequest
from .exceptions import (
    ValidationError, NotFoundError, ReferenceNotFoundError,
    InvalidOrganizerError, InvalidStatusTransitionError, DependencyUnavailableError,
)

def _err(code, message, status, details=None):
    return jsonify({"error": {"code": code, "message": message,
                              "details": details or {}}}), status

def _register_error_handlers(app):
    @app.errorhandler(ValidationError)
    def _validation(e):
        details = {"field": e.field} if e.field else {}
        return _err("VALIDATION_ERROR", str(e), 422, details)

    @app.errorhandler(ReferenceNotFoundError)
    def _reference(e):
        return _err("REFERENCE_NOT_FOUND", str(e), 422)

    @app.errorhandler(InvalidOrganizerError)
    def _invalid_org(e):
        return _err("INVALID_ORGANIZER", str(e), 422)

    @app.errorhandler(InvalidStatusTransitionError)
    def _invalid_transition(e):
        return _err("INVALID_STATUS_TRANSITION", str(e), 422)

    @app.errorhandler(NotFoundError)
    def _not_found(e):
        return _err("NOT_FOUND", str(e), 404)

    @app.errorhandler(DependencyUnavailableError)
    def _dependency(e):
        return _err("DEPENDENCY_UNAVAILABLE", str(e), 503)

    @app.errorhandler(BadRequest)
    def _bad_request(e):
        return _err("MALFORMED_JSON", "Corpo della richiesta non è JSON valido", 400)
```

### Formato errore standard (REQ-EVT-17.5)

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "Descrizione leggibile dell'errore",
    "details": {}
  }
}
```

Tutte le risposte con body usano `Content-Type: application/json` e nomi di campo in
`snake_case` (REQ-EVT-17.1, 17.2).

---

## Repository Implementations

### MemoryRepository

```
Struttura dati: dict Python  {id: event_dict}
Stato: in-memory, perso al riavvio del processo (REQ-EVT-16.1: nessun file su disco)

find_by_id(id)    → self._store.get(id)
find_all(filters) → lista di event che soddisfano status/city (o tutti se filters vuoto)
save(event)       → self._store[event['id']] = event; return event
delete(id)        → return self._store.pop(id, None) is not None
```

### JsonRepository

```
File: {DATA_DIR}/events.json
Formato: { "events": [ { event_dict }, ... ] }
Libreria: solo stdlib `json` (REQ-EVT-16.2)
DATA_DIR creata se assente (REQ-EVT-16.7)
Strategia: atomic read-modify-write (write su file temporaneo + os.replace)
```

### SqliteRepository

```
File: {DATA_DIR}/events.db
Schema: tabella `events` (vedere Data Models)
Libreria: solo stdlib `sqlite3` (REQ-EVT-16.3)
DATA_DIR creata se assente (REQ-EVT-16.7)
Connessione: aperta e chiusa per ogni operazione

find_by_id(id)    → SELECT * FROM events WHERE id = ?
find_all(filters) → SELECT * FROM events [WHERE status=? AND lower(city)=lower(?)]
save(event)       → INSERT OR REPLACE INTO events VALUES (...)   (price come stringa)
delete(id)        → DELETE FROM events WHERE id = ?; return rowcount > 0
```

Tutti e tre i backend rispettano lo **stesso contratto** `EventRepository`: cambiare
`STORAGE_BACKEND` non richiede modifiche a Service o Router (REQ-EVT-16.4). Il Router
non accede mai direttamente al backend: passa sempre per il Repository tramite il
Service (REQ-EVT-16.5, 16.6).

---

## Testing Strategy

### Approccio duale

Il testing usa due tipologie complementari:

1. **Unit test** — esempi specifici, casi limite, conformità al contratto per ogni
   endpoint, regole di business in isolamento.
2. **Property-based test** — verifica delle 16 property universali con input generati.

A queste si aggiungono gli **integration test propri**, obbligatori perché questo
servizio chiama un altro servizio reale.

Libreria PBT: **Hypothesis**. Ogni property test usa `@settings(max_examples=100)`.
Le chiamate HTTP verso lo user-service nei unit test sono mockate con la libreria
`responses` (per `UserServiceClient`) oppure con un `user_client` mockato
(`unittest.mock`) iniettato via `create_app`.

Obiettivo coverage: **≥ 80%** del package `app` (`pytest --cov=app`).

### Unit Test — `services/event_service/tests/unit/`

#### `test_repository.py`

CRUD completo parametrizzato sui tre backend con la fixture `tmp_path`:

```python
@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", request.param)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # reimporta config/get_repository per leggere l'env aggiornato
    return get_repository()

def test_save_and_find_by_id(repo):
    ev = make_event()
    repo.save(ev)
    assert repo.find_by_id(ev["id"]) == ev

def test_delete_removes_event(repo):
    ev = make_event()
    repo.save(ev)
    assert repo.delete(ev["id"]) is True
    assert repo.find_by_id(ev["id"]) is None

def test_find_all_filters_city_case_insensitive(repo):
    repo.save(make_event(city="Milano"))
    repo.save(make_event(city="Roma"))
    result = repo.find_all({"city": "milano"})
    assert all(e["city"].lower() == "milano" for e in result)
```

#### `test_service.py`

Verifica ogni regola `REQ-EVT-B*` in isolamento, con `user_client` mockato
(`unittest.mock.MagicMock`) e `MemoryRepository` reale (o repository mockato):

```python
# REQ-EVT-B01 — organizer inesistente → REFERENCE_NOT_FOUND
def test_create_raises_reference_not_found():
    uc = MagicMock()
    uc.validate_organizer.side_effect = ReferenceNotFoundError("...")
    svc = EventService(MemoryRepository(), uc)
    with pytest.raises(ReferenceNotFoundError):
        svc.create_event(valid_body())

# REQ-EVT-B02 — role != organizer → INVALID_ORGANIZER
def test_create_raises_invalid_organizer():
    uc = MagicMock()
    uc.validate_organizer.side_effect = InvalidOrganizerError("...")
    svc = EventService(MemoryRepository(), uc)
    with pytest.raises(InvalidOrganizerError):
        svc.create_event(valid_body())

# REQ-EVT-B03 — end_date < start_date → ValidationError
def test_create_rejects_end_before_start():
    svc = EventService(MemoryRepository(), MagicMock())
    with pytest.raises(ValidationError):
        svc.create_event(valid_body(start_date="2026-05-10", end_date="2026-05-01"))

# REQ-EVT-B04 — transizione non ammessa → InvalidStatusTransitionError
def test_cancelled_to_published_rejected():
    svc, ev = _seed_event(status="cancelled")
    with pytest.raises(InvalidStatusTransitionError):
        svc.update_event(ev["id"], {"status": "published"})

# REQ-EVT-8.5/8.7 — PATCH senza organizer o con organizer uguale NON chiama user-service
def test_patch_without_organizer_does_not_call_user_service():
    uc = MagicMock()
    svc, ev = _seed_event(user_client=uc)
    svc.update_event(ev["id"], {"title": "Nuovo titolo valido"})
    uc.validate_organizer.assert_not_called()

# REQ-EVT-B06 — total dopo i filtri, prima della paginazione
def test_list_total_counts_filtered_before_pagination():
    svc = _seed_many(status_mix=True)
    res = svc.list_events({"status": "draft"}, page=1, page_size=2)
    assert res["total"] == expected_draft_count
    assert len(res["items"]) <= 2
```

#### `test_user_client.py`

Test del `UserServiceClient` con la libreria `responses`, verificando la mappatura
delle risposte/errori (REQ-EVT-B01, B02, B05):

```python
import responses, requests
from unittest.mock import patch

BASE = "http://localhost:5001"

@responses.activate
def test_get_user_200_returns_dict():
    responses.add(responses.GET, f"{BASE}/api/v1/users/u1",
                  json={"id": "u1", "role": "organizer"}, status=200)
    assert UserServiceClient(BASE).get_user("u1")["role"] == "organizer"

@responses.activate
def test_get_user_404_raises_reference_not_found():
    responses.add(responses.GET, f"{BASE}/api/v1/users/u1",
                  json={"error": {"code": "NOT_FOUND"}}, status=404)
    with pytest.raises(ReferenceNotFoundError):
        UserServiceClient(BASE).get_user("u1")

@responses.activate
def test_get_user_500_raises_dependency_unavailable():
    responses.add(responses.GET, f"{BASE}/api/v1/users/u1", status=500)
    with pytest.raises(DependencyUnavailableError):
        UserServiceClient(BASE).get_user("u1")

def test_get_user_timeout_raises_dependency_unavailable():
    with patch("app.user_client.requests.get",
               side_effect=requests.exceptions.Timeout):
        with pytest.raises(DependencyUnavailableError):
            UserServiceClient(BASE).get_user("u1")

def test_get_user_connection_error_raises_dependency_unavailable():
    with patch("app.user_client.requests.get",
               side_effect=requests.exceptions.ConnectionError):
        with pytest.raises(DependencyUnavailableError):
            UserServiceClient(BASE).get_user("u1")

@responses.activate
def test_validate_organizer_rejects_wrong_role():
    responses.add(responses.GET, f"{BASE}/api/v1/users/u1",
                  json={"id": "u1", "role": "attendee"}, status=200)
    with pytest.raises(InvalidOrganizerError):
        UserServiceClient(BASE).validate_organizer("u1")
```

Il timeout esatto di 2 secondi (REQ-EVT-B05, 14.1) si verifica sia controllando che il
client sia costruito con `timeout=2.0`, sia simulando `requests.exceptions.Timeout`.

#### `test_routes.py`

Endpoint HTTP con `user_client` mockato iniettato via `create_app`; almeno **una**
chiamata `assert_matches_contract("event", method, path, response)` per endpoint. Per i
casi 503 si inietta un `user_client` che solleva `DependencyUnavailableError`:

```python
from contracts.validator import assert_matches_contract

def make_client(user_client=None):
    return create_app(repo=MemoryRepository(),
                      user_client=user_client or _ok_user_client()).test_client()

def test_create_event_201():
    client = make_client()
    resp = client.post("/api/v1/events", json=valid_body())
    assert resp.status_code == 201
    assert resp.headers["Location"].startswith("/api/v1/events/")
    assert_matches_contract("event", "POST", "/api/v1/events", resp)

def test_create_event_422_validation():
    client = make_client()
    resp = client.post("/api/v1/events", json={"title": "x"})  # troppo corto + mancanti
    assert resp.status_code == 422
    assert_matches_contract("event", "POST", "/api/v1/events", resp)

def test_create_event_503_dependency_down():
    uc = MagicMock()
    uc.validate_organizer.side_effect = DependencyUnavailableError("down")
    client = make_client(user_client=uc)
    resp = client.post("/api/v1/events", json=valid_body())
    assert resp.status_code == 503
    assert_matches_contract("event", "POST", "/api/v1/events", resp)

def test_get_event_404():
    client = make_client()
    resp = client.get("/api/v1/events/00000000-0000-4000-8000-000000000000")
    assert resp.status_code == 404
    assert_matches_contract("event", "GET", "/api/v1/events/{id}", resp)
```

Endpoint coperti: `GET /health`, `POST`, `GET` (lista), `GET` (singolo), `PUT`,
`PATCH`, `DELETE`.

#### `test_properties.py`

Property-based con Hypothesis; ogni test corrisponde a **una** property del design e
riporta il tag di riferimento:

```python
from hypothesis import given, settings

# Feature: event-service, Property 1: la creazione preserva l'input e applica i default
@given(body=valid_event_bodies())
@settings(max_examples=100)
def test_create_preserves_input(body):
    """Feature: event-service, Property 1: la creazione preserva l'input e applica i default"""
    svc = EventService(MemoryRepository(), _ok_user_client())
    ev = svc.create_event(body)
    assert ev["status"] == body.get("status", "draft")
    assert ev["description"] == body.get("description", None)
    assert is_uuid_v4(ev["id"])
    assert is_iso_utc(ev["created_at"]) and is_iso_utc(ev["updated_at"])

# Feature: event-service, Property 8: solo le transizioni ammesse sono accettate
@given(current=event_status(), new=event_status())
@settings(max_examples=100)
def test_status_transition_rule(current, new):
    """Feature: event-service, Property 8: solo le transizioni ammesse sono accettate"""
    svc, ev = _seed_event(status=current)
    allowed = current == new or (current, new) in ALLOWED_TRANSITIONS
    if allowed:
        assert svc.update_event(ev["id"], {"status": new})["status"] == new
    else:
        with pytest.raises(InvalidStatusTransitionError):
            svc.update_event(ev["id"], {"status": new})

# Feature: event-service, Property 16: i tre backend producono risultati equivalenti
@given(ops=crud_operation_sequences())
@settings(max_examples=100)
def test_backends_equivalent(ops, tmp_path):
    """Feature: event-service, Property 16: i tre backend producono risultati equivalenti"""
    results = [run_ops(make_repo(b, tmp_path), ops)
               for b in ("memory", "json", "sqlite")]
    assert results[0] == results[1] == results[2]
```

Tag format: **Feature: event-service, Property {N}: {testo property}**. Ogni property
del design corrisponde a esattamente 1 test property-based.

### Integration Test propri — `services/event_service/tests/integration/`

L'event-service **chiama** lo user-service, quindi sono richiesti integration test con
servizi reali (Platform Standards + `structure.md`). Una fixture pytest avvia
**user-service** ed **event-service** come subprocess reali su porte libere:

```python
import socket, subprocess, sys, time, requests, pytest

def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def _wait_health(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"http://localhost:{port}/health", timeout=1).status_code == 200:
                return
        except requests.exceptions.RequestException:
            time.sleep(0.2)
    raise RuntimeError(f"service on {port} not healthy")

@pytest.fixture
def services():
    user_port, event_port = _free_port(), _free_port()

    user_env = {**os.environ, "PORT": str(user_port), "STORAGE_BACKEND": "memory"}
    user_proc = subprocess.Popen([sys.executable, "-m", "app"],
                                 cwd="services/user_service", env=user_env)

    event_env = {**os.environ, "PORT": str(event_port),
                 "USER_SERVICE_URL": f"http://localhost:{user_port}",
                 "STORAGE_BACKEND": "memory"}
    event_proc = subprocess.Popen([sys.executable, "-m", "app"],
                                  cwd="services/event_service", env=event_env)
    try:
        _wait_health(user_port)
        _wait_health(event_port)
        yield {"user": user_port, "event": event_port}
    finally:
        # teardown: termina i subprocess e attende la chiusura
        for p in (event_proc, user_proc):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
```

Casi minimi richiesti, mappati ai test di collaudo e alle regole di business:

| Test proprio | Scenario | Esito atteso | Collaudo | Regola |
|---|---|---|---|---|
| Caso positivo | crea un `organizer` reale in user-service, poi crea un event con quell'`organizer_id` | 201 + risorsa Event | **IT-E01** | REQ-EVT-B01/B02 |
| Riferimento inesistente | `organizer_id` UUID casuale non presente in user-service | 422 `REFERENCE_NOT_FOUND` | **IT-E02** | REQ-EVT-B01 |
| Dipendenza spenta | avvia event-service con `USER_SERVICE_URL` verso una porta chiusa, poi POST event | 503 `DEPENDENCY_UNAVAILABLE` | **IT-E08** | REQ-EVT-B05 |

```python
def test_it_e01_create_with_real_organizer(services):
    up, ep = services["user"], services["event"]
    org = requests.post(f"http://localhost:{up}/api/v1/users",
                        json={"first_name": "O", "last_name": "R",
                              "email": "o@x.com", "role": "organizer"}).json()
    resp = requests.post(f"http://localhost:{ep}/api/v1/events",
                         json=valid_body(organizer_id=org["id"]))
    assert resp.status_code == 201                              # IT-E01, B01/B02

def test_it_e02_reference_not_found(services):
    ep = services["event"]
    resp = requests.post(f"http://localhost:{ep}/api/v1/events",
                         json=valid_body(organizer_id=str(uuid.uuid4())))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REFERENCE_NOT_FOUND"  # IT-E02, B01

def test_it_e08_dependency_unavailable(dead_dependency_event_service):
    ep = dead_dependency_event_service   # USER_SERVICE_URL → porta chiusa
    resp = requests.post(f"http://localhost:{ep}/api/v1/events", json=valid_body())
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"  # IT-E08, B05
```

Per lo scenario "dipendenza spenta" si usa una fixture dedicata che avvia solo
l'event-service con `USER_SERVICE_URL` puntato a una porta libera **non** in ascolto
(connessione rifiutata → 503), con lo stesso pattern di teardown dei subprocess.

### Comandi

```bash
# Unit test con coverage (dalla root del servizio)
cd services/event_service
pytest tests/unit --cov=app --cov-report=term-missing

# Solo property-based test
pytest tests/unit/test_properties.py -v

# Integration test propri del servizio
pytest tests/integration -v
```

---

## Contract Reference

Il contratto definitivo è `contracts/openapi/event-service.yaml` (non modificabile).
Tutti i test del router includono almeno una chiamata `assert_matches_contract("event",
method, path, response)` per endpoint. Il validator viene importato dal path relativo
alla root del progetto (stesso pattern dello user-service):

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
from contracts.validator import assert_matches_contract
```

### Endpoint dichiarati nel contratto

| Metodo | Path | Status possibili |
|---|---|---|
| `GET` | `/health` | 200 |
| `POST` | `/api/v1/events` | 201, 400, 422, 503 |
| `GET` | `/api/v1/events` | 200, 422 |
| `GET` | `/api/v1/events/{id}` | 200, 404 |
| `PUT` | `/api/v1/events/{id}` | 200, 404, 422, 503 |
| `PATCH` | `/api/v1/events/{id}` | 200, 404, 422, 503 |
| `DELETE` | `/api/v1/events/{id}` | 204, 404 |

Ogni risposta restituita dal servizio deve superare la validazione dello schema
`Draft7Validator` applicata dal validator sugli schemi del contratto (schemi `Health`,
`Event`, `EventCreate`, `EventUpdate`, `EventPage`, `Error`, tutti con
`additionalProperties: false`) — REQ-EVT-17.6, 17.7.
