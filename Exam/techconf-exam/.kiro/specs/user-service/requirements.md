# Requirements Document

## Introduction

Il **user-service** è il microservizio anagrafica della piattaforma TechConf.
Gestisce il ciclo di vita degli utenti (partecipanti, relatori, organizzatori) ed è la
fonte di verità per le identità all'interno del sistema.
Espone API REST sotto il base path `/api/v1/users` sulla porta definita dalla variabile
d'ambiente `PORT` (valore di sviluppo: 5001).

Il servizio **non chiama** altri microservizi; è invece chiamato da `event-service`,
`registration-service` e `notification-service` per verificare l'esistenza di un utente.

Il contratto definitivo degli endpoint è il file
`contracts/openapi/user-service.yaml` (non modificabile).

---

## Glossary

| Termine | Definizione |
|---|---|
| **User_Service** | Il microservizio oggetto di questo documento. |
| **User** | Risorsa che rappresenta un utente registrato nella piattaforma TechConf. |
| **Role** | Ruolo associato all'utente: `attendee`, `speaker`, oppure `organizer`. |
| **UUID v4** | Identificativo univoco universale versione 4, generato dal server e non accettato in input. |
| **ISO 8601 UTC** | Formato timestamp `YYYY-MM-DDTHH:MM:SSZ` usato per `created_at` e `updated_at`. |
| **STORAGE_BACKEND** | Variabile d'ambiente che seleziona il backend di persistenza: `memory`, `json` o `sqlite`. |
| **DATA_DIR** | Variabile d'ambiente che indica la directory in cui salvare i file json/sqlite (default `./data`). |
| **Router** | Livello HTTP del servizio: parsing del body, validazione dei tipi, costruzione della risposta. |
| **Service Layer** | Livello contenente tutte le regole di business (`REQ-USR-B*`). |
| **Repository** | Livello di accesso alla persistenza; nasconde il backend attivo al Service Layer. |

---

## Requirements

### Requirement 1: Infrastruttura e configurazione del servizio

**User Story:** Come operatore della piattaforma TechConf, voglio che il user-service sia
avviabile tramite il manifest `services.yaml` e configurabile esclusivamente via variabili
d'ambiente, così da poterlo deployare e testare in ambienti diversi senza modificare il
codice sorgente.

#### Acceptance Criteria

1. THE User_Service SHALL leggere la porta di ascolto esclusivamente dalla variabile
   d'ambiente `PORT` e non accettare mai un valore hard-coded.
2. THE User_Service SHALL leggere il backend di persistenza dalla variabile d'ambiente
   `STORAGE_BACKEND` con valore di default `memory`; i valori ammessi sono `memory`,
   `json` e `sqlite`.
3. THE User_Service SHALL leggere la directory dei file di dati dalla variabile d'ambiente
   `DATA_DIR` con valore di default `./data`.
4. THE User_Service SHALL esporre un file `run.py` nella root del servizio che istanzia
   l'applicazione Flask e la avvia sulla porta letta da `PORT`.
5. THE User_Service SHALL dichiarare le proprie dipendenze runtime (`flask`, `requests`) e
   di test (`pytest`, `pytest-cov`, `responses`) in un file `requirements.txt` interno alla
   propria directory.
6. WHEN `STORAGE_BACKEND` è impostato a `json` o `sqlite`, THE User_Service SHALL salvare
   i file di dati nella directory indicata da `DATA_DIR`.
7. IF `STORAGE_BACKEND` ha un valore diverso da `memory`, `json` e `sqlite`, THEN
   THE User_Service SHALL avviarsi con il backend `memory` come fallback sicuro.

---

### Requirement 2: Health check

**User Story:** Come client o orchestratore, voglio interrogare un endpoint `/health` per
verificare che il user-service sia in esecuzione e raggiungibile, così da poter rilevare
rapidamente eventuali anomalie.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `GET /health`, THE User_Service SHALL rispondere con
   stato HTTP `200` e corpo JSON `{"status": "ok", "service": "user-service"}`.
2. THE User_Service SHALL rispettare lo schema `Health` definito nel contratto OpenAPI
   (`additionalProperties: false`, campi obbligatori `status` e `service`).

---

### Requirement 3: Creazione di un utente (POST /api/v1/users)

**User Story:** Come client della piattaforma, voglio registrare un nuovo utente fornendo
nome, cognome, email e ruolo, così da poterlo referenziare negli altri microservizi.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `POST /api/v1/users` con body JSON valido, THE
   User_Service SHALL creare la risorsa `User`, assegnare un `id` UUID v4 generato dal
   server, impostare `created_at` e `updated_at` al timestamp UTC corrente, e rispondere
   con stato HTTP `201`.
2. WHEN la creazione ha successo, THE User_Service SHALL includere nella risposta
   l'header `Location` con il valore `/api/v1/users/{id}` e il body contenente la
   risorsa `User` appena creata.
3. IF il body della richiesta non è JSON valido, THEN THE User_Service SHALL rispondere
   con stato HTTP `400` e corpo `{"error": {"code": "MALFORMED_JSON", "message": "...",
   "details": {}}}`.
4. IF uno o più campi obbligatori (`first_name`, `last_name`, `email`) sono assenti o
   non rispettano i vincoli di lunghezza o formato, THEN THE User_Service SHALL rispondere
   con stato HTTP `422` e codice errore `VALIDATION_ERROR`.
5. IF `first_name` ha lunghezza inferiore a 1 o superiore a 50 caratteri, THEN THE
   User_Service SHALL rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
6. IF `last_name` ha lunghezza inferiore a 1 o superiore a 50 caratteri, THEN THE
   User_Service SHALL rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
7. IF `company` è presente e supera i 100 caratteri, THEN THE User_Service SHALL
   rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
8. IF `role` è presente e il suo valore non è `attendee`, `speaker` o `organizer`, THEN
   THE User_Service SHALL rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
9. WHEN `role` non è fornito nel body, THE User_Service SHALL assegnare il valore
   predefinito `attendee` alla risorsa creata.
10. IF l'indirizzo email fornito (confrontato in modo case-insensitive) è già presente
    nell'archivio, THEN THE User_Service SHALL rispondere con stato HTTP `409` e codice
    errore `EMAIL_ALREADY_EXISTS` — **REQ-USR-B01**.
11. WHEN la risorsa `User` viene creata, THE User_Service SHALL normalizzare e salvare il
    campo `email` in lettere minuscole — **REQ-USR-B02**.
12. THE User_Service SHALL non accettare nel body un campo `id` fornito dal client; il
    campo viene ignorato o rifiutato con `422 VALIDATION_ERROR`.

---

### Requirement 4: Lista degli utenti (GET /api/v1/users)

**User Story:** Come client della piattaforma, voglio ottenere l'elenco paginato degli
utenti con la possibilità di filtrare per ruolo o indirizzo email, così da ricercare
facilmente utenti specifici.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `GET /api/v1/users`, THE User_Service SHALL rispondere
   con stato HTTP `200` e corpo JSON conforme allo schema `UserPage`:
   `{"items": [...], "page": <intero>, "page_size": <intero>, "total": <intero>}`.
2. WHEN il parametro `page` non è fornito, THE User_Service SHALL utilizzare il valore
   predefinito `1`.
3. WHEN il parametro `page_size` non è fornito, THE User_Service SHALL utilizzare il
   valore predefinito `20`.
4. IF `page_size` supera il valore `100`, THEN THE User_Service SHALL rispondere con stato
   HTTP `422` e codice `VALIDATION_ERROR`.
5. IF `page` o `page_size` hanno valori non interi o inferiori a `1`, THEN THE
   User_Service SHALL rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
6. WHEN il parametro di query `role` è fornito con un valore valido (`attendee`, `speaker`,
   `organizer`), THE User_Service SHALL restituire solo gli utenti con quel ruolo —
   **REQ-USR-B03**.
7. WHEN il parametro di query `email` è fornito, THE User_Service SHALL restituire solo
   gli utenti il cui campo `email` corrisponde esattamente al valore fornito (confronto
   case-insensitive) — **REQ-USR-B03**.
8. WHEN entrambi i parametri `role` ed `email` sono forniti, THE User_Service SHALL
   applicare entrambi i filtri in combinazione (AND logico) — **REQ-USR-B03**.
9. IF il parametro `role` contiene un valore non appartenente all'enum `Role`, THEN THE
   User_Service SHALL rispondere con stato HTTP `422` e codice `VALIDATION_ERROR`.
10. WHILE non esistono utenti che soddisfano i criteri di ricerca, THE User_Service SHALL
    rispondere con stato HTTP `200` e campo `items` uguale a `[]` e `total` uguale a `0`.

---

### Requirement 5: Lettura di un singolo utente (GET /api/v1/users/{id})

**User Story:** Come client della piattaforma, voglio recuperare i dati di un singolo
utente tramite il suo identificativo UUID, così da visualizzarne il profilo o verificarne
l'esistenza.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `GET /api/v1/users/{id}` e l'utente con quell'`id`
   esiste, THE User_Service SHALL rispondere con stato HTTP `200` e il body JSON contenente
   la risorsa `User` completa.
2. IF l'utente con l'`id` specificato non esiste nell'archivio, THEN THE User_Service
   SHALL rispondere con stato HTTP `404` e corpo
   `{"error": {"code": "NOT_FOUND", "message": "...", "details": {}}}`.
3. THE User_Service SHALL restituire nella risposta tutti i campi della risorsa `User`
   definiti nel contratto OpenAPI, inclusi `id`, `created_at` e `updated_at`.

---

### Requirement 6: Sostituzione completa di un utente (PUT /api/v1/users/{id})

**User Story:** Come client della piattaforma, voglio sostituire completamente il profilo
di un utente esistente fornendo tutti i campi scrivibili, così da aggiornarne i dati in
modo atomico.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `PUT /api/v1/users/{id}` con body JSON valido e
   l'utente esiste, THE User_Service SHALL sostituire tutti i campi scrivibili della
   risorsa, aggiornare `updated_at` al timestamp UTC corrente e rispondere con stato
   HTTP `200` e la risorsa `User` aggiornata.
2. IF l'utente con l'`id` specificato non esiste nell'archivio, THEN THE User_Service
   SHALL rispondere con stato HTTP `404` e codice `NOT_FOUND`.
3. IF il body della richiesta non è JSON valido, THEN THE User_Service SHALL rispondere
   con stato HTTP `400` e codice `MALFORMED_JSON`.
4. IF uno o più campi obbligatori (`first_name`, `last_name`, `email`) sono assenti o
   violano i vincoli di lunghezza o formato, THEN THE User_Service SHALL rispondere con
   stato HTTP `422` e codice `VALIDATION_ERROR`.
5. IF la nuova email (confrontata in modo case-insensitive) è già associata a un utente
   diverso da quello che si sta aggiornando, THEN THE User_Service SHALL rispondere con
   stato HTTP `409` e codice `EMAIL_ALREADY_EXISTS` — **REQ-USR-B01**.
6. WHEN la sostituzione ha successo, THE User_Service SHALL normalizzare e salvare il
   campo `email` in lettere minuscole — **REQ-USR-B02**.
7. WHEN `role` non è fornito nel body della richiesta PUT, THE User_Service SHALL
   assegnare il valore predefinito `attendee`.

---

### Requirement 7: Aggiornamento parziale di un utente (PATCH /api/v1/users/{id})

**User Story:** Come client della piattaforma, voglio aggiornare selettivamente uno o più
campi del profilo di un utente esistente senza dover reinviare l'intera risorsa, così da
ridurre il traffico di rete e minimizzare il rischio di sovrascritture indesiderate.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `PATCH /api/v1/users/{id}` con body JSON valido e
   l'utente esiste, THE User_Service SHALL aggiornare solo i campi presenti nel body,
   lasciare invariati gli altri campi, aggiornare `updated_at` e rispondere con stato
   HTTP `200` e la risorsa `User` aggiornata.
2. IF l'utente con l'`id` specificato non esiste nell'archivio, THEN THE User_Service
   SHALL rispondere con stato HTTP `404` e codice `NOT_FOUND`.
3. IF il body della richiesta non è JSON valido, THEN THE User_Service SHALL rispondere
   con stato HTTP `400` e codice `MALFORMED_JSON`.
4. IF un campo fornito viola i vincoli di lunghezza, formato o enum definiti nel contratto
   OpenAPI, THEN THE User_Service SHALL rispondere con stato HTTP `422` e codice
   `VALIDATION_ERROR`.
5. IF il campo `email` è presente nel body PATCH e (confrontato in modo case-insensitive)
   è già associato a un utente diverso, THEN THE User_Service SHALL rispondere con stato
   HTTP `409` e codice `EMAIL_ALREADY_EXISTS` — **REQ-USR-B01**.
6. WHEN il campo `email` è presente nel body PATCH e la modifica ha successo, THE
   User_Service SHALL normalizzare e salvare l'email in lettere minuscole —
   **REQ-USR-B02**.

---

### Requirement 8: Eliminazione di un utente (DELETE /api/v1/users/{id})

**User Story:** Come amministratore della piattaforma, voglio eliminare definitivamente il
profilo di un utente tramite il suo identificativo, così da gestire la cancellazione degli
account.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta `DELETE /api/v1/users/{id}` e l'utente con quell'`id`
   esiste, THE User_Service SHALL eliminare la risorsa e rispondere con stato HTTP `204`
   senza body.
2. IF l'utente con l'`id` specificato non esiste nell'archivio, THEN THE User_Service
   SHALL rispondere con stato HTTP `404` e codice `NOT_FOUND`.

---

### Requirement 9: Unicità dell'email (case-insensitive)

**User Story:** Come client della piattaforma, voglio che due utenti non possano avere lo
stesso indirizzo email (indipendentemente da maiuscole e minuscole), così da garantire
l'univocità delle identità e prevenire duplicati.

#### Acceptance Criteria

1. WHEN viene ricevuta una richiesta di creazione o aggiornamento con un campo `email` il
   cui valore, convertito in minuscolo, coincide con l'email di un utente già esistente
   (con id diverso), THE User_Service SHALL rifiutare l'operazione con stato HTTP `409` e
   codice `EMAIL_ALREADY_EXISTS`.
2. THE User_Service SHALL eseguire il confronto di unicità dell'email in modo
   case-insensitive; ad esempio `User@Example.com` e `user@example.com` sono considerati
   duplicati.

---

### Requirement 10: Normalizzazione dell'email

**User Story:** Come client della piattaforma, voglio che le email vengano sempre
memorizzate in minuscolo, così da garantire la coerenza dei dati indipendentemente da come
l'email viene fornita in input.

#### Acceptance Criteria

1. WHEN viene creata o aggiornata una risorsa `User` con un campo `email`, THE User_Service
   SHALL convertire il valore in lettere minuscole prima di salvarlo nel repository.
2. THE User_Service SHALL restituire il campo `email` in lettere minuscole in tutte le
   risposte che includono la risorsa `User`.

---

### Requirement 11: Filtri sulla lista utenti

**User Story:** Come client della piattaforma, voglio filtrare l'elenco degli utenti per
ruolo e/o indirizzo email, così da trovare rapidamente un sottoinsieme di utenti senza
dover scaricare l'intera collezione.

#### Acceptance Criteria

1. WHEN il parametro di query `role` è fornito, THE User_Service SHALL restituire
   esclusivamente gli utenti il cui campo `role` corrisponde al valore specificato.
2. WHEN il parametro di query `email` è fornito, THE User_Service SHALL restituire
   esclusivamente gli utenti il cui campo `email` corrisponde al valore specificato, con
   confronto case-insensitive.
3. WHEN entrambi i parametri `role` ed `email` sono forniti, THE User_Service SHALL
   applicare entrambi i filtri contemporaneamente (AND logico).
4. WHEN un filtro è attivo, THE User_Service SHALL aggiornare il campo `total` nella
   risposta paginata in modo che rifletta il numero totale di utenti che soddisfano i
   criteri di filtro (non il totale assoluto dell'archivio).

---

### Requirement 12: Persistenza intercambiabile

**User Story:** Come sviluppatore, voglio poter cambiare il backend di persistenza tramite
una variabile d'ambiente senza modificare la logica di business, così da testare con
`memory` e deployare con `json` o `sqlite` senza refactoring.

#### Acceptance Criteria

1. THE User_Service SHALL implementare il Repository Pattern: il Service Layer interagisce
   solo con metodi ad alto livello (`find_by_id`, `save`, `list_all`, `delete`); il
   Repository è l'unico componente che conosce il backend attivo.
2. WHEN `STORAGE_BACKEND=memory`, THE User_Service SHALL mantenere i dati in memoria
   (dict Python); i dati vengono persi al riavvio.
3. WHEN `STORAGE_BACKEND=json`, THE User_Service SHALL leggere e scrivere i dati in un
   file JSON nella directory `DATA_DIR`; deve usare solo la libreria standard `json`.
4. WHEN `STORAGE_BACKEND=sqlite`, THE User_Service SHALL leggere e scrivere i dati in un
   file SQLite nella directory `DATA_DIR`; deve usare solo la libreria standard `sqlite3`.
5. THE User_Service SHALL garantire che il cambio di `STORAGE_BACKEND` non richieda
   alcuna modifica al Service Layer o al Router.

---

### Requirement 13: Formato della risposta e conformità al contratto

**User Story:** Come client della piattaforma, voglio che ogni risposta del user-service
rispetti esattamente il contratto OpenAPI `user-service.yaml`, così da poter fare
affidamento su una struttura stabile e validabile.

#### Acceptance Criteria

1. THE User_Service SHALL restituire il `Content-Type: application/json` in tutte le
   risposte con body.
2. THE User_Service SHALL usare `snake_case` per tutti i nomi di campo JSON.
3. THE User_Service SHALL formattare i timestamp `created_at` e `updated_at` in formato
   ISO 8601 UTC (es. `2026-10-15T09:30:00Z`).
4. THE User_Service SHALL usare il formato `{"error": {"code": "UPPER_SNAKE",
   "message": "...", "details": {}}}` per tutti i messaggi di errore.
5. THE User_Service SHALL rispettare lo schema `additionalProperties: false` del contratto
   OpenAPI: nessun campo extra viene restituito nelle risposte.
