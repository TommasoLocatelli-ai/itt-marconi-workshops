# Design Document — registration-service

## Overview

Il **registration-service** gestisce le iscrizioni degli utenti agli eventi TechConf tramite API REST sotto `/api/v1/registrations`. Ascolta sulla porta letta da `PORT` (default `5003`) e dipende via HTTP da `user-service` ed `event-service`.

Fonti di verità del design:
- `.kiro/specs/registration-service/requirements.md` per requisiti e regole `REQ-REG-B01`–`REQ-REG-B09`;
- `contracts/openapi/registration-service.yaml` per endpoint, body e status ammessi;
- `.kiro/steering/structure.md` e `platform-standards.md` per struttura del monorepo e standard comuni;
- `contracts/validator.py` per la verifica contrattuale nei test.

Il servizio usa Python, Flask e `requests`. La persistenza è selezionabile tra `memory`, `json` e `sqlite` senza modificare Router o Service Layer. Nessun servizio importa codice di un altro microservizio: la comunicazione avviene esclusivamente via HTTP.

I body JSON usano `snake_case`, gli identificativi sono UUID v4, i timestamp sono UTC ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` e gli importi sono numeri EUR normalizzati a due decimali.

## Architecture

Architettura a tre livelli con due adapter HTTP:

```text
HTTP Client
    |
    v
Router Flask (routes.py) ---> Service Layer (service.py) ---> Repository
                                   |                           memory/json/sqlite
                                   +--> UserServiceClient  ---> user-service
                                   +--> EventServiceClient ---> event-service

config.py ---> create_app(...) ---> componenti configurati/iniettati
```

| Livello | Responsabilità | Esclusioni |
|---|---|---|
| Router | HTTP in/out, parsing, query, status, header ed envelope errori | Nessuna regola B01–B09; nessun accesso diretto allo storage |
| Service | Validazione applicativa, orchestrazione e tutte le regole B01–B09 | Nessun oggetto Flask; nessuna conoscenza del backend |
| Repository | CRUD, filtri e aggregazioni equivalenti sui tre backend | Nessuna chiamata HTTP o regola di business |
| Client HTTP | URL, timeout, GET e classificazione degli errori remoti | Nessuna decisione specifica POST/stats |

### Flusso POST

Ordine esatto di `create_registration`:
1. validazione locale di schema, UUID e campi consentiti;
2. `get_user(user_id)` (`REQ-REG-B01`);
3. `get_event(event_id)` (`REQ-REG-B02`);
4. verifica `event.status == "published"` (`REQ-REG-B03`);
5. verifica assenza di una Registration `confirmed` duplicata (`REQ-REG-B04`);
6. verifica `count_confirmed(event_id) < event.capacity` (`REQ-REG-B05`);
7. copia `event.price` in `amount` (`REQ-REG-B06`);
8. crea con `status=confirmed`, UUID v4 e timestamp (`REQ-REG-B07`), quindi salva.

Il prezzo proviene dalla stessa risposta evento già usata per stato e capienza: non viene eseguita una seconda chiamata. Solo dopo tutti i controlli il Router restituisce `201`, body Registration e `Location`.

## Components and Interfaces

### `app/__init__.py`

Interfaccia pubblica:

```python
def create_app(repo=None, user_client=None, event_client=None) -> Flask: ...
```

La factory usa i componenti iniettati o, in loro assenza, crea Repository e client dai valori di `config.py`; costruisce `RegistrationService(repo, user_client, event_client)`, registra blueprint e gestori delle eccezioni. La dependency injection evita rete e filesystem reali nei test. I componenti possono essere esposti tramite `app.extensions`, senza globali condivisi.

### `app/config.py`

È l'unico modulo che legge `os.environ`.

| Variabile | Default | Uso |
|---|---|---|
| `PORT` | `5003` | Porta Flask |
| `USER_SERVICE_URL` | `http://localhost:5001` | Base URL user-service |
| `EVENT_SERVICE_URL` | `http://localhost:5002` | Base URL event-service |
| `STORAGE_BACKEND` | `memory` | Backend `memory`/`json`/`sqlite` |
| `DATA_DIR` | `./data` | Directory dei backend persistenti |

Gli URL sono iniettati dalla factory e mai hard-coded nei client (`REQ-REG-B09`).

### `app/models.py`

Contiene la dataclass `Registration`, `REGISTRATION_STATUSES = ("confirmed", "cancelled")`, `to_dict()` senza proprietà aggiuntive, generazione con `uuid.uuid4()`, `utc_now_iso()` e normalizzazione dell'importo a due decimali. Non accede a Flask, rete o Repository.

### `app/exceptions.py`

Eccezioni applicative:
- `ValidationError`;
- `NotFoundError`;
- `RemoteNotFoundError(resource)`, interna ai client;
- `ReferenceNotFoundError`;
- `EventNotOpenError`;
- `AlreadyRegisteredError`;
- `EventFullError`;
- `InvalidStatusTransitionError`;
- `DependencyUnavailableError`.

`RemoteNotFoundError` rappresenta solo un 404 remoto. Il Service lo converte in base al caso d'uso; gli error handler Flask convertono le altre eccezioni in status ed `Error_Response`.

### `app/http_clients.py`

```python
class UserServiceClient:
    def get_user(self, user_id: str) -> dict: ...

class EventServiceClient:
    def get_event(self, event_id: str) -> dict: ...
```

Entrambi ricevono `base_url` e `timeout=2.0`. Il comportamento è definito in `HTTP Dependency Handling`.

### `app/routes.py`

Il Router:
- distingue JSON POST malformato da errori semantici;
- valida/converte `page` e `page_size` e raccoglie i filtri;
- invoca esclusivamente metodi del Service;
- imposta `Location: /api/v1/registrations/{id}` sul `201`;
- restituisce DELETE `204` senza body;
- gestisce PUT come `405 METHOD_NOT_ALLOWED` senza chiamare il Service;
- serializza sempre l'envelope errore standard.

| Metodo e path | Azione | Stati |
|---|---|---|
| `GET /health` | health statico | `200` |
| `POST /api/v1/registrations` | `create_registration` | `201`, `400`, `409`, `422`, `503` |
| `GET /api/v1/registrations` | `list_registrations` | `200`, `422` |
| `GET /api/v1/registrations/stats` | `registration_stats` | `200`, `404`, `422`, `503` |
| `GET /api/v1/registrations/{id}` | `get_registration` | `200`, `404` |
| `PATCH /api/v1/registrations/{id}` | `update_registration` | `200`, `404`, `422` |
| `DELETE /api/v1/registrations/{id}` | `delete_registration` | `204`, `404` |
| `PUT /api/v1/registrations/{id}` | errore Router | `405` |

### `app/service.py`

```python
RegistrationService(repo, user_client, event_client)
create_registration(data) -> dict
list_registrations(filters, page, page_size) -> dict
get_registration(registration_id) -> dict
update_registration(registration_id, status) -> dict
delete_registration(registration_id) -> None
registration_stats(event_id) -> dict
```

`create_registration(data)` applica l'ordine descritto in Architecture. Un 404 utente/evento diventa `ReferenceNotFoundError`; nessuna scrittura precede il completamento dei controlli. `amount` è lo snapshot di `event.price` e non cambia dopo successive modifiche del prezzo.

`list_registrations(filters, page, page_size)` combina `user_id`, `event_id` e `status` in AND. `total` è calcolato dopo i filtri e prima della paginazione; una pagina senza risultati restituisce `items: []` mantenendo `total`.

`get_registration(id)` usa `repo.find_by_id` e solleva `NotFoundError` se assente.

`update_registration(id, status)` consente `confirmed -> cancelled` e lo stesso stato come richiesta idempotente. `cancelled -> confirmed` solleva `InvalidStatusTransitionError`. Ogni PATCH valido aggiorna `updated_at`; possono cambiare solo `status` e `updated_at`, mentre nel caso idempotente cambia esclusivamente `updated_at` (`REQ-REG-B07`).

`delete_registration(id)` elimina o solleva `NotFoundError`. Cancellare o eliminare una Registration confirmed la esclude dai conteggi successivi e libera capienza (`REQ-REG-B05`).

`registration_stats(event_id)` recupera l'evento una volta; un 404 remoto diventa `NotFoundError`. Conta solo le confirmed e restituisce `{event_id, capacity, confirmed, available}`, con `available=max(capacity-confirmed,0)` (`REQ-REG-B08`).

| Regola | Implementazione principale |
|---|---|
| `REQ-REG-B01` | utente esistente, verificato prima dell'evento |
| `REQ-REG-B02` | evento esistente durante POST |
| `REQ-REG-B03` | evento esclusivamente `published` |
| `REQ-REG-B04` | `exists_confirmed(user_id,event_id)`; le cancelled non bloccano |
| `REQ-REG-B05` | `count_confirmed`, capacity e rilascio posto su cancel/delete |
| `REQ-REG-B06` | `amount` copiato una sola volta da `event.price` |
| `REQ-REG-B07` | stato iniziale e transizioni/idempotenza PATCH |
| `REQ-REG-B08` | recupero evento e calcolo stats |
| `REQ-REG-B09` | propagazione uniforme di `DependencyUnavailableError` |

### `app/__main__.py` e `run.py`

Avviano `create_app()` su `0.0.0.0` usando esclusivamente `app.config.PORT`. `run.py` è l'entry point dichiarabile in `services.yaml`; nessuno dei due contiene logica applicativa.

## Data Models

### Registration

| Campo | Tipo API | Origine/vincoli |
|---|---|---|
| `id` | string UUID | UUID v4 server-generated, read-only |
| `user_id` | string UUID | obbligatorio nel POST |
| `event_id` | string UUID | obbligatorio nel POST |
| `amount` | number | EUR a due decimali da `event.price`, read-only |
| `status` | enum | `confirmed`/`cancelled`, inizialmente `confirmed` |
| `created_at` | date-time | UTC ISO 8601, read-only e immutabile |
| `updated_at` | date-time | UTC ISO 8601, aggiornato dal PATCH |

Il POST accetta solo `user_id` ed `event_id`; il PATCH solo `status`. Campi mancanti, extra/read-only o valori non validi producono `422 VALIDATION_ERROR`.

### Paginazione e stats

```text
RegistrationPage  = {items: Registration[], page: int, page_size: int, total: int}
RegistrationStats = {event_id: UUID, capacity: int, confirmed: int, available: int}
```

Default `page=1`, `page_size=20`; vincoli `page>=1` e `1<=page_size<=100`. `confirmed` conta solo record confirmed, `available` non è mai negativo e nessuna risposta ammette proprietà aggiuntive.

## HTTP Dependency Handling

I client usano sempre `requests.get(url, timeout=2.0)` e costruiscono l'URL dalla base iniettata con `rstrip("/")`.

| Client | Endpoint | `200` | `404` | timeout/ConnectionError/`5xx`/altro status |
|---|---|---|---|---|
| User | `/api/v1/users/{id}` | restituisce utente | `RemoteNotFoundError("user")` | `DependencyUnavailableError` |
| Event | `/api/v1/events/{id}` | restituisce evento | `RemoteNotFoundError("event")` | `DependencyUnavailableError` |

Per `REQ-REG-B09`, timeout, connessione rifiutata, `5xx` e stato inatteso diventano sempre `503 DEPENDENCY_UNAVAILABLE`. Il timeout esatto è `2.0` secondi per ogni chiamata di POST o stats.

La decisione sul 404 resta nel Service:
- POST registration: user/event assente -> `ReferenceNotFoundError` -> `422 REFERENCE_NOT_FOUND` (`REQ-REG-B01/B02`);
- GET stats: event assente -> `NotFoundError` -> `404 NOT_FOUND` (`REQ-REG-B08`).

Il client non duplica logica di caso d'uso. Un evento presente con `status` assente o diverso da `published` produce invece `422 EVENT_NOT_OPEN` nel Service (`REQ-REG-B03`).

## Error Handling

Formato uniforme:

```json
{"error":{"code":"UPPER_SNAKE","message":"Descrizione leggibile","details":{}}}
```

| Situazione | HTTP | Codice |
|---|---:|---|
| JSON POST malformato | 400 | `MALFORMED_JSON` |
| Body, UUID, query o paginazione non validi | 422 | `VALIDATION_ERROR` |
| Registration locale assente | 404 | `NOT_FOUND` |
| User/event remoto assente su POST | 422 | `REFERENCE_NOT_FOUND` |
| Evento non published o senza status | 422 | `EVENT_NOT_OPEN` |
| Coppia user/event già confirmed | 409 | `ALREADY_REGISTERED` |
| Confirmed `>= capacity` | 409 | `EVENT_FULL` |
| Transizione di stato non ammessa | 422 | `INVALID_STATUS_TRANSITION` |
| Evento remoto assente su stats | 404 | `NOT_FOUND` |
| Dipendenza indisponibile | 503 | `DEPENDENCY_UNAVAILABLE` |
| PUT su Registration | 405 | `METHOD_NOT_ALLOWED` |

Lo stesso 404 di event-service indica quindi un riferimento non valido nel POST (`422`) ma una risorsa stats inesistente (`404`). `RemoteNotFoundError` conserva la distinzione fino al Service. Gli error handler Flask sono l'unico punto che costruisce l'envelope; `details` è sempre un oggetto JSON.

## Repository Implementations

Interfaccia minima comune:

```python
class RegistrationRepository:
    def find_by_id(self, registration_id): ...
    def find_all(self, filters): ...
    def save(self, registration): ...
    def delete(self, registration_id): ...
    def exists_confirmed(self, user_id, event_id): ...
    def count_confirmed(self, event_id): ...
```

`find_all` applica i filtri in AND e restituisce una sequenza stabile; il Service calcola `total` e pagina. Le query aggregate considerano solo `status="confirmed"`.

### MemoryRegistrationRepository

Usa un `dict` indicizzato per `id`, non crea file e perde i dati al riavvio. Restituisce copie per evitare modifiche esterne accidentali.

### JsonRegistrationRepository

Usa `{DATA_DIR}/registrations.json` nel formato `{"registrations":[...]}` e solo la stdlib `json`. Crea `DATA_DIR`; ogni mutazione usa read-modify-write su file temporaneo nella stessa directory seguito da `os.replace`.

### SqliteRegistrationRepository

Usa `{DATA_DIR}/registrations.db`, crea la directory e usa solo `sqlite3`.

```sql
registrations(
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  amount TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
```

`amount` è una stringa decimale canonica a due cifre nello storage e torna un JSON number in output. Indici:
- `(user_id,event_id,status)` per `exists_confirmed`;
- `(event_id,status)` per capacità e stats.

`get_repository()` usa `json` o `sqlite` quando richiesto e ricade su memory per valore assente, `memory` o non riconosciuto. Il cambio backend non tocca Router o Service.

## Testing Strategy

Non si introduce Hypothesis né property-based testing: il servizio è soprattutto CRUD, HTTP e persistenza. Si usano test unitari example-based, test di contratto e integrazione reale con stdlib, Flask, requests, pytest, pytest-cov e responses.

### Unit — `services/registration_service/tests/unit/`

`test_repository.py`, parametrizzato `memory/json/sqlite` con `tmp_path`:
- CRUD e riapertura dei backend persistenti;
- filtri singoli/combinati in AND;
- `exists_confirmed`, `count_confirmed` ed esclusione cancelled;
- creazione `DATA_DIR` e formato JSON.

`test_http_clients.py`, con `responses` e patch di `requests.get`:
- `200`, `404`, `5xx` e stato inatteso per entrambi i client;
- `Timeout` e `ConnectionError` -> `DependencyUnavailableError`;
- URL da base iniettata e asserzione `timeout=2.0` (`REQ-REG-B09`).

`test_service.py`, con client mockati:
- validazione locale e ordine user -> event -> business rules;
- utente/evento assente (`B01/B02`) ed evento draft/missing status (`B03`);
- duplicato e nuova iscrizione dopo cancelled (`B04`);
- capacity, soli confirmed e posto liberato da cancel/delete (`B05`);
- copia/immutabilità storica di amount (`B06`);
- stato iniziale, transizione, idempotenza e riattivazione vietata (`B07`);
- formula stats e 404 evento (`B08`);
- indisponibilità di entrambi i client (`B09`);
- filtri, total pre-paginazione, pagina vuota e not-found locale.

`test_routes.py`, con dependency injection:
- health, parsing, query, `Location`, DELETE senza body e PUT 405;
- status e codici di errore principali;
- almeno una `assert_matches_contract("registration", method, path, response)` per ogni endpoint: health, collection POST/GET, stats, item GET/PATCH/DELETE/PUT.

Comando: `pytest tests/unit --cov=app --cov-report=term-missing`. Coverage obiettivo: `>=80%` del package `app`.

### Integration — `services/registration_service/tests/integration/`

Una fixture avvia realmente user-service, event-service e registration-service con `subprocess.Popen` su porte libere. Inietta `PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, esegue polling `/health` con limite temporale e nel teardown usa `terminate`, `wait`, poi `kill` se necessario. Nessun mock HTTP.

Scenari minimi:
- organizer/utente ed evento published reali -> Registration `201`;
- utente o evento inesistente -> `422 REFERENCE_NOT_FOUND`;
- evento draft -> `422 EVENT_NOT_OPEN`;
- dipendenza spenta -> `503 DEPENDENCY_UNAVAILABLE`;
- `amount` uguale al prezzo al momento della creazione;
- se economico, duplicato, capacity/cancellazione e stats.

Il validator e i contratti restano immutati.

## Contract Reference

`contracts/openapi/registration-service.yaml` è la fonte di verità non modificabile. Il design non aggiunge endpoint, status o proprietà.

| Metodo | Path | Status contrattuali |
|---|---|---|
| `GET` | `/health` | `200` |
| `POST` | `/api/v1/registrations` | `201`, `400`, `409`, `422`, `503` |
| `GET` | `/api/v1/registrations` | `200`, `422` |
| `GET` | `/api/v1/registrations/stats` | `200`, `404`, `422`, `503` |
| `GET` | `/api/v1/registrations/{id}` | `200`, `404` |
| `PUT` | `/api/v1/registrations/{id}` | `405` |
| `PATCH` | `/api/v1/registrations/{id}` | `200`, `404`, `422` |
| `DELETE` | `/api/v1/registrations/{id}` | `204`, `404` |

Il `201` include `Location: /api/v1/registrations/{id}`; il `204` non ha body. Gli schemi `Health`, `Registration`, `RegistrationPage`, `RegistrationStats` ed `Error` non ammettono proprietà aggiuntive.

`contracts/validator.py` è non modificabile. I test Router usano `assert_matches_contract("registration", method, path, response)` per verificare status e schema di ogni endpoint.