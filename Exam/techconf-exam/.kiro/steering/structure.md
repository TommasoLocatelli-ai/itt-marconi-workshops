# TechConf — Repository Structure

Questo file risponde alle domande guida della sezione 7 della traccia e costituisce la
**fonte di verità** per l'organizzazione del codice. Kiro deve rispettare queste decisioni
in ogni task generato da una spec.

---

## Repository e confini dei servizi

### Scelta: monorepo

Tutti i microservizi vivono in un unico repository, nella cartella `services/`.

**Motivazioni:**
- La suite di collaudo (`tests/integration/`) e i contratti OpenAPI sono già nel repo
  template: un monorepo evita di dover gestire sottomoduli git o riferimenti incrociati.
- I 5 servizi condividono le stesse versioni di Python e delle dipendenze di test; un
  unico ambiente virtuale semplifica il setup.
- L'aggiunta dei servizi opzionali (`feedback_service`, `notification_service`) richiede
  solo una nuova sottocartella, senza creare nuovi repository.

### Confini visibili tra servizi

Ogni servizio ha la propria sottocartella sotto `services/`. Nessun servizio importa
codice di un altro servizio: la comunicazione avviene **esclusivamente via HTTP**.
Condividere un modulo Python tra servizi è vietato; se la logica è identica, si duplica.

### Layout del repository

```
techconf-exam/
├── contracts/
│   ├── openapi/               # Contratti OpenAPI — NON modificare
│   └── validator.py           # Helper assert_matches_contract — NON modificare
├── services/
│   ├── user_service/          # Microservizio obbligatorio — porta 5001
│   ├── event_service/         # Microservizio obbligatorio — porta 5002
│   ├── registration_service/  # Microservizio obbligatorio — porta 5003
│   ├── feedback_service/      # Microservizio opzionale — porta 5004
│   └── notification_service/  # Microservizio opzionale — porta 5005
├── tests/
│   └── integration/           # Suite di collaudo del docente — NON modificare
├── services.yaml              # Manifest letto dalla suite di collaudo
├── services.example.yaml
├── CHECKSUMS.sha256
├── BUGS.md
└── README.md
```

---

## Struttura interna di ogni microservizio

Ogni servizio segue la stessa struttura a tre livelli. Esempio per `user_service`:

```
services/user_service/
├── app/
│   ├── __init__.py        # Factory Flask (create_app)
│   ├── config.py          # Lettura variabili d'ambiente (PORT, STORAGE_BACKEND, ...)
│   ├── routes.py          # Router Flask — solo HTTP in/out, nessuna logica di business
│   ├── service.py         # Service layer — tutte le regole REQ-*-B*
│   ├── repository.py      # Repository pattern — astrazioni memory / json / sqlite
│   └── models.py          # Dataclass o dict schema delle risorse
├── tests/
│   ├── unit/
│   │   ├── test_routes.py        # Test degli endpoint HTTP (mock del service layer)
│   │   ├── test_service.py       # Test delle regole di business (mock del repository)
│   │   └── test_repository.py   # Test del repository con tutti e tre i backend
│   └── integration/
│       └── test_<svc>_integration.py  # Test con servizi reali avviati in subprocess
├── requirements.txt       # flask, requests (runtime) + pytest, pytest-cov, responses (test)
└── run.py                 # Entry point: legge PORT da env e avvia Flask
```

### I tre livelli e le loro responsabilità

| Livello | File | Responsabilità | Cosa NON deve fare |
|---------|------|----------------|--------------------|
| **Router** | `routes.py` | Parse del body JSON, validazione dei tipi HTTP, costruzione della risposta (status code, header `Location`, formato errore) | Contenere regole di business REQ-* |
| **Service** | `service.py` | Implementare tutte le regole `REQ-*-B*`: unicità, transizioni di stato, chiamate agli altri servizi, controllo capienza | Costruire oggetti Flask Response, conoscere il backend di persistenza |
| **Repository** | `repository.py` | Tradurre le operazioni CRUD nel backend attivo (`memory` / `json` / `sqlite`) | Contenere logica di business; essere chiamato dal router direttamente |

### Dove vivono le regole REQ-*-B*

**Tutte** le regole di business (`REQ-USR-B01`, `REQ-EVT-B02`, ecc.) si trovano
esclusivamente nel **service layer** (`service.py`). Il router non conosce queste regole;
il repository non le conosce. Questo rende ogni regola facile da trovare e da testare
in isolamento.

---

## Codice condiviso e duplicazione

**Scelta: duplicazione controllata — nessuna libreria shared.**

Ogni servizio è autonomo: formato degli errori, paginazione, client HTTP e validazione
sono implementati nel singolo servizio.

**Motivazioni:**
- Un modulo shared creerebbe accoppiamento tra servizi: una modifica alla libreria comune
  richiederebbe di rilanciare i test di tutti i servizi.
- Se un servizio dovesse essere estratto in un repository separato (o consegnato a un
  altro team), funzionerebbe senza dipendenze esterne al proprio package.
- La duplicazione è limitata: i pattern sono semplici (una funzione `make_error`,
  una funzione `paginate`) e cambiano raramente.

---

## Persistenza e Repository Pattern

Il **Repository Pattern** isola completamente la logica di storage dal resto
dell'applicazione. Il service layer chiama solo metodi ad alto livello
(`repo.find_by_id`, `repo.save`, `repo.list_all`); non sa nulla di dict, file JSON
o tabelle SQLite.

### Selezione del backend

In `repository.py` (o in `__init__.py` tramite la factory):

```python
def get_repository():
    backend = os.environ.get("STORAGE_BACKEND", "memory")
    if backend == "json":
        return JsonRepository()
    elif backend == "sqlite":
        return SqliteRepository()
    else:
        return MemoryRepository()
```

Il service layer chiama `get_repository()` una sola volta (o riceve il repository
per dependency injection nei test). Cambiare `STORAGE_BACKEND` non tocca nessun
altro file.

### File di dati

I file JSON e SQLite vengono scritti nella directory `DATA_DIR`
(default `./data`, relativa alla `cwd` del servizio). La cartella `data/` è in
`.gitignore`.

---

## Configurazione e variabili d'ambiente

Ogni servizio legge tutta la configurazione in **un unico modulo** (`app/config.py`):

```python
PORT                 = int(os.environ.get("PORT", 5001))
STORAGE_BACKEND      = os.environ.get("STORAGE_BACKEND", "memory")
DATA_DIR             = os.environ.get("DATA_DIR", "./data")
USER_SERVICE_URL     = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
EVENT_SERVICE_URL    = os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")
REGISTRATION_SERVICE_URL = os.environ.get("REGISTRATION_SERVICE_URL", "http://localhost:5003")
```

Nessun'altra parte del codice chiama `os.environ` direttamente.

### Comando di avvio

Tutti i servizi usano lo stesso pattern in `run.py`:

```python
from app import create_app
from app.config import PORT

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=PORT)
```

In `services.yaml`:

```yaml
user_service:
  cwd: services/user_service
  command: python run.py
```

### Dipendenze Python

Un **singolo file `requirements.txt` per servizio** (dentro `services/<svc>/`).
Tutti i servizi usano le stesse librerie e versioni; se in futuro divergessero,
l'isolamento è già garantito dall'approccio per-servizio.

---

## Test

### Unit test (`services/<svc>/tests/unit/`)

- **`test_routes.py`**: verifica i codici di stato HTTP, il formato JSON della risposta
  e almeno 1 chiamata `assert_matches_contract` per endpoint. Il service layer è
  mockato con `unittest.mock`.
- **`test_service.py`**: verifica ogni regola `REQ-*-B*` in isolamento. Il repository
  è mockato.
- **`test_repository.py`**: verifica le operazioni CRUD con **tutti e tre** i backend
  (`memory`, `json`, `sqlite`) usando la fixture `tmp_path` di pytest per i file
  temporanei. Nessun mock: si usa il repository reale.

Tutti i test di regressione dei bug usano il marker `@pytest.mark.req("REQ-*-B*")`
o includono l'ID nel nome della funzione.

### Integration test propri (`services/<svc>/tests/integration/`)

Per i servizi che chiamano altri servizi (`event_service`, `registration_service`):
- Una fixture pytest avvia i servizi dipendenti come **subprocess** su porte libere
  (usando `socket` per trovare una porta libera, `subprocess.Popen` per avviarli,
  e un loop di health-check per attendere che siano pronti).
- Ogni file di integration test verifica almeno: 1 caso positivo, 1 riferimento
  inesistente (422), 1 dipendenza spenta (503).
- La fixture fa `teardown` dei subprocess al termine dei test.

### Comandi

```bash
# Unit test di un singolo servizio (dalla root del servizio)
cd services/user_service
pytest tests/unit --cov=app --cov-report=term-missing

# Integration test propri di un servizio
pytest services/event_service/tests/integration -v

# Suite di collaudo del docente (dalla root del repo)
pytest tests/integration -m mandatory -v
```

---

## Spec e tracciabilità

- Una spec Kiro per microservizio: `.kiro/specs/<svc>/` (con `requirements.md`,
  `design.md`, `tasks.md`).
- Gli ID `REQ-*-B*` compaiono nei `requirements.md`, nei docstring/nomi dei test e
  nei commenti del service layer. Per trovare il codice che implementa `REQ-REG-B05`:
  1. `grep -r "REQ-REG-B05" services/registration_service/` → `service.py` + test.
- `structure.md` (questo file) contiene decisioni valide per tutto il repository.
  `design.md` di ogni servizio contiene decisioni specifiche di quel servizio
  (es. schema SQLite, endpoint chiamati, gestione degli errori specifici).

---

## Git

- `data/` in `.gitignore` (file JSON e SQLite generati a runtime).
- Sequenza di commit per ogni servizio:
  1. `spec(<svc>): requirements`
  2. `spec(<svc>): design`
  3. `spec(<svc>): tasks`
  4. `feat(<svc>): <descrizione task> [T-NN]` (uno per task)
  5. `test(<svc>): <descrizione>` per i test aggiunti separatamente
  6. `fix(<svc>): <descrizione> (closes #N)` per i bug
