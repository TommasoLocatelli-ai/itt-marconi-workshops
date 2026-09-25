# Platform Standards

> Regole vincolanti per **tutti** i microservizi TechConf.
> Queste norme non possono essere derogate da decisioni specifiche di un singolo servizio.

---

## Avvio dei servizi

- Un file `services.yaml` nella root dichiara, per ogni servizio implementato, la cartella di lavoro (`cwd`) e il comando di avvio (`command`).
- La suite di collaudo legge `services.yaml` e inietta in ogni servizio le variabili `PORT` e `*_SERVICE_URL`.
- Ogni servizio **deve** ascoltare sulla porta indicata dalla variabile d'ambiente `PORT` — la porta non va mai hard-coded.

---

## Base path

```
/api/v1/<risorsa>
```

---

## Formato

- Corpo di richiesta e risposta sempre in **JSON**.
- Tutti i nomi di campo in **`snake_case`**.

---

## Identificativi

- `id` **UUID v4** generato dal server.
- L'`id` non viene mai accettato in input dal client.

---

## Timestamp

- Formato **ISO 8601 UTC**: `2026-10-15T09:30:00Z`.
- Ogni risorsa espone `created_at` e `updated_at` (read-only).

---

## Date e importi

- Date: **`YYYY-MM-DD`**
- Importi: **numerici con 2 decimali** (es. `149.00`); valuta implicita EUR.

---

## Paginazione

Parametri di query: `?page=1&page_size=20` (massimo `page_size` = 100).

Struttura della risposta:

```json
{
  "items": [...],
  "page": 1,
  "page_size": 20,
  "total": 57
}
```

---

## Formato degli errori

Tutti gli errori devono usare questa struttura:

```json
{
  "error": {
    "code": "UPPER_SNAKE",
    "message": "Descrizione leggibile",
    "details": {}
  }
}
```

---

## Codici di stato HTTP

| Codice | Utilizzo |
|--------|----------|
| `201` | Creazione riuscita (+ header `Location`) |
| `200` | Lettura o modifica riuscita |
| `204` | Cancellazione riuscita |
| `400` | JSON malformato |
| `404` | Risorsa non trovata — `NOT_FOUND` |
| `405` | Metodo HTTP non previsto |
| `409` | Conflitto (es. duplicato) |
| `422` | Errore di validazione o regola di business — `VALIDATION_ERROR` / `REFERENCE_NOT_FOUND` / altri codici specifici |
| `503` | Dipendenza non raggiungibile — `DEPENDENCY_UNAVAILABLE` |

---

## Chiamate tra servizi

- Gli URL dei servizi dipendenti vengono letti **esclusivamente** da variabili d'ambiente:
  - `USER_SERVICE_URL` (default: `http://localhost:5001`)
  - `EVENT_SERVICE_URL` (default: `http://localhost:5002`)
  - `REGISTRATION_SERVICE_URL` (default: `http://localhost:5003`)
- **Timeout**: 2 secondi per ogni chiamata HTTP uscente.
- Mappatura degli errori ricevuti dai servizi dipendenti:
  - `404` dal servizio chiamato → `422 REFERENCE_NOT_FOUND`
  - Timeout, connessione rifiutata o `5xx` → `503 DEPENDENCY_UNAVAILABLE`

---

## Health check

Ogni servizio deve esporre:

```
GET /health
```

Risposta attesa (`200 OK`):

```json
{
  "status": "ok",
  "service": "<nome-del-servizio>"
}
```

---

## Persistenza

- Controllata dalla variabile d'ambiente **`STORAGE_BACKEND`**:
  - `memory` (default) — in-memory, nessun file su disco
  - `json` — file JSON in `DATA_DIR` (default `./data`)
  - `sqlite` — file SQLite in `DATA_DIR` (default `./data`)
- `DATA_DIR` va esclusa da git (`.gitignore`).
- **Solo librerie standard** (`json`, `sqlite3`): nessun DBMS da installare o configurare.
- Il cambio di backend **non deve richiedere modifiche alla logica di business**.

---

## Dipendenze Python

| Tipo | Librerie |
|------|----------|
| Runtime | `flask`, `requests` |
| Test | `pytest`, `pytest-cov`, `responses` |
