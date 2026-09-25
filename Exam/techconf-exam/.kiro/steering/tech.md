# TechConf — Technology Stack

## Linguaggio e runtime

- **Python 3.12** — versione unica per tutti i microservizi

## Dipendenze runtime

| Libreria | Versione minima | Utilizzo |
|---|---|---|
| `flask` | ≥ 3.0 | Framework HTTP per ogni microservizio |
| `requests` | ≥ 2.31 | Chiamate HTTP tra microservizi |

## Dipendenze di test

| Libreria | Utilizzo |
|---|---|
| `pytest` | Test runner per unit test e integration test |
| `pytest-cov` | Misurazione della code coverage (obiettivo: ≥ 80%) |
| `responses` | Mock delle chiamate HTTP verso altri servizi negli unit test |

Nessuna altra dipendenza esterna è ammessa. In particolare è vietato l'uso di DBMS esterni o ORM di terze parti.

## Persistenza

La persistenza è controllata dalla variabile d'ambiente **`STORAGE_BACKEND`** e deve essere intercambiabile senza modificare la logica di business.

| Valore | Backend | Note |
|---|---|---|
| `memory` (default) | In-memory (dict Python) | Nessun file su disco; dati persi al riavvio |
| `json` | File JSON | File in `DATA_DIR` (default `./data`); usa solo la libreria standard `json` |
| `sqlite` | SQLite | File in `DATA_DIR`; usa solo la libreria standard `sqlite3` |

### Regole di implementazione

- Il cambio di `STORAGE_BACKEND` non deve richiedere alcuna modifica alla logica di business.
- I file di dati (`json`/`sqlite`) vanno salvati in `DATA_DIR` (default `./data`) ed esclusi da git (`.gitignore`).
- Vietato usare librerie ORM o driver esterni: solo `json` e `sqlite3` della standard library.
- Il repository (classe/modulo) è l'unico punto del codice che conosce il backend attivo.

## Configurazione via variabili d'ambiente

| Variabile | Default | Descrizione |
|---|---|---|
| `PORT` | (obbligatorio) | Porta su cui il servizio ascolta — sempre letta da env |
| `STORAGE_BACKEND` | `memory` | Backend di persistenza |
| `DATA_DIR` | `./data` | Directory per i file json/sqlite |
| `USER_SERVICE_URL` | `http://localhost:5001` | URL base di user-service |
| `EVENT_SERVICE_URL` | `http://localhost:5002` | URL base di event-service |
| `REGISTRATION_SERVICE_URL` | `http://localhost:5003` | URL base di registration-service |

Tutte le variabili di configurazione devono essere lette **in un unico punto** (es. modulo `config.py`) e mai hard-coded nel codice applicativo.

## Formato dati

- **JSON** per tutti i corpi di richiesta/risposta
- Campi in `snake_case`
- Timestamp ISO 8601 UTC (es. `2026-10-15T09:30:00Z`)
- Date `YYYY-MM-DD`
- Importi numerici con 2 decimali (es. `149.00`)

## Strumenti di sviluppo

- **Kiro IDE** — spec-driven development (Requirements-First obbligatorio)
- **Git** — commit convenzionali: `spec(…)`, `feat(…)`, `test(…)`, `fix(…)`, `docs(…)`, `chore(…)`
