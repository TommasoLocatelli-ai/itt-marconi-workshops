# Requirements Document

## Introduction

Il **registration-service** gestisce le iscrizioni degli utenti agli eventi TechConf tramite API REST sotto `/api/v1/registrations`. Il servizio ascolta sulla porta configurata da `PORT`, usa user-service ed event-service come dipendenze HTTP e rispetta il contratto non modificabile `contracts/openapi/registration-service.yaml`.

## Glossary

| Termine | Definizione |
|---|---|
| **Registration_Service** | Il microservizio oggetto del documento, identificato come `registration-service`. |
| **Registration** | Iscrizione composta esclusivamente da `id`, `user_id`, `event_id`, `amount`, `status`, `created_at` e `updated_at`. |
| **User_Service** | Dipendenza HTTP che verifica l'esistenza dell'utente. |
| **Event_Service** | Dipendenza HTTP che fornisce esistenza, stato, capienza e prezzo dell'evento. |
| **Registration_Status** | Stato `confirmed` oppure `cancelled`. |
| **Campo_read_only** | Campo generato dal server: `id`, `amount`, `status`, `created_at` oppure `updated_at`. |
| **Paginazione** | Suddivisione tramite `page` e `page_size`, con risposta `items`, `page`, `page_size` e `total`. |
| **Error_Response** | JSON `{"error":{"code":"UPPER_SNAKE","message":"...","details":{}}}`. |
| **Repository** | Interfaccia di persistenza indipendente dai backend `memory`, `json` e `sqlite`. |
| **Contratto_OpenAPI** | Il file `contracts/openapi/registration-service.yaml`, fonte di verità per l'API. |
| **UUID_v4** | Identificativo UUID versione 4 generato dal server. |
| **ISO_8601_UTC** | Formato timestamp UTC `YYYY-MM-DDTHH:MM:SSZ`. |

## Requirements

### Requirement 1: Configurazione e health check

**User Story:** Come operatore, voglio configurare e monitorare Registration_Service, così da eseguirlo nell'ambiente TechConf.

#### Acceptance Criteria

1. WHEN Registration_Service viene avviato, THE Registration_Service SHALL leggere `PORT`, `USER_SERVICE_URL`, `EVENT_SERVICE_URL`, `STORAGE_BACKEND` e `DATA_DIR` dalle variabili d'ambiente tramite un unico componente di configurazione.
2. WHEN `PORT` vale `5003`, THE Registration_Service SHALL ascoltare sulla porta `5003`.
3. WHEN Registration_Service riceve `GET /health`, THE Registration_Service SHALL rispondere con stato HTTP `200` e JSON `{"status":"ok","service":"registration-service"}`.

### Requirement 2: Modello e creazione tramite POST

**User Story:** Come client, voglio creare un'iscrizione valida, così da registrare un utente a un evento.

#### Acceptance Criteria

1. IF il body di `POST /api/v1/registrations` contiene JSON malformato, THEN THE Registration_Service SHALL rispondere con stato HTTP `400` e Error_Response con codice `MALFORMED_JSON`.
2. IF il body POST omette `user_id` o `event_id` oppure contiene un valore non UUID, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
3. IF il body POST contiene un Campo_read_only o un campo diverso da `user_id` ed `event_id`, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
4. WHEN Registration_Service elabora un POST, THE Registration_Service SHALL applicare nell'ordine la validazione locale, la verifica utente `REQ-REG-B01`, le verifiche evento `REQ-REG-B02`, `REQ-REG-B03` e `REQ-REG-B06`, il controllo duplicato `REQ-REG-B04`, il controllo capienza `REQ-REG-B05` e la creazione.
5. WHEN tutte le validazioni POST hanno esito positivo, THE Registration_Service SHALL rispondere con stato HTTP `201`, body Registration e header `Location` uguale a `/api/v1/registrations/{id}`.
6. WHEN Registration_Service crea Registration, THE Registration_Service SHALL generare `id` come UUID_v4 e `created_at` e `updated_at` come timestamp ISO_8601_UTC corrente.

### Requirement 3: Lettura, aggiornamento ed eliminazione

**User Story:** Come client, voglio consultare, cancellare o aggiornare lo stato di un'iscrizione, così da gestirne il ciclo di vita.

#### Acceptance Criteria

1. WHEN Registration_Service riceve `GET /api/v1/registrations/{id}` per una Registration esistente, THE Registration_Service SHALL rispondere con stato HTTP `200` e body Registration.
2. IF `GET /api/v1/registrations/{id}` identifica una Registration inesistente, THEN THE Registration_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
3. IF il body PATCH omette `status`, contiene campi diversi da `status` o usa un valore fuori da Registration_Status, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
4. WHEN Registration_Service riceve `PATCH /api/v1/registrations/{id}` valido per una Registration esistente, THE Registration_Service SHALL rispondere con stato HTTP `200` e body Registration aggiornato.
5. WHEN Registration_Service riceve `DELETE /api/v1/registrations/{id}` per una Registration esistente, THE Registration_Service SHALL eliminare Registration e rispondere con stato HTTP `204` senza body.
6. IF PATCH o DELETE identifica una Registration inesistente, THEN THE Registration_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
7. WHEN Registration_Service riceve `PUT /api/v1/registrations/{id}`, THE Registration_Service SHALL rispondere con stato HTTP `405` e Error_Response con codice `METHOD_NOT_ALLOWED`.

### Requirement 4: Elenco, filtri e paginazione

**User Story:** Come client, voglio elencare e filtrare le iscrizioni, così da ottenere un insieme di risultati controllato.

#### Acceptance Criteria

1. WHEN Registration_Service riceve `GET /api/v1/registrations` con parametri validi, THE Registration_Service SHALL rispondere con stato HTTP `200` e JSON contenente `items`, `page`, `page_size` e `total`.
2. WHEN `page` o `page_size` sono omessi, THE Registration_Service SHALL usare rispettivamente `1` e `20`.
3. IF `page` non è un intero maggiore o uguale a `1` oppure `page_size` non è un intero compreso tra `1` e `100`, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
4. IF `user_id` o `event_id` non è un UUID oppure `status` non appartiene a Registration_Status, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
5. WHEN più filtri tra `user_id`, `event_id` e `status` sono presenti, THE Registration_Service SHALL combinarli mediante AND logico.
6. WHEN Registration_Service calcola `total`, THE Registration_Service SHALL contare le Registration filtrate prima di applicare la Paginazione.
7. WHILE nessuna Registration soddisfa i filtri o la pagina richiesta, THE Registration_Service SHALL rispondere con stato HTTP `200` e `items` uguale a `[]`.

### Requirement 5: Esistenza utente — REQ-REG-B01

**User Story:** Come gestore, voglio accettare iscrizioni solo per utenti esistenti, così da evitare riferimenti non validi.

#### Acceptance Criteria

1. WHEN un body POST supera la validazione locale, THE Registration_Service SHALL chiamare `GET {USER_SERVICE_URL}/api/v1/users/{user_id}` prima di verificare l'evento — **REQ-REG-B01**.
2. IF User_Service risponde con stato HTTP `404`, THEN THE Registration_Service SHALL interrompere il POST e rispondere con stato HTTP `422` e Error_Response con codice `REFERENCE_NOT_FOUND` — **REQ-REG-B01**.

### Requirement 6: Esistenza evento — REQ-REG-B02

**User Story:** Come gestore, voglio accettare iscrizioni solo per eventi esistenti, così da evitare riferimenti non validi.

#### Acceptance Criteria

1. WHEN User_Service conferma l'utente, THE Registration_Service SHALL chiamare `GET {EVENT_SERVICE_URL}/api/v1/events/{event_id}` — **REQ-REG-B02**.
2. IF Event_Service risponde con stato HTTP `404` durante un POST, THEN THE Registration_Service SHALL interrompere il POST e rispondere con stato HTTP `422` e Error_Response con codice `REFERENCE_NOT_FOUND` — **REQ-REG-B02**.

### Requirement 7: Evento aperto — REQ-REG-B03

**User Story:** Come organizzatore, voglio consentire iscrizioni solo a eventi pubblicati, così da proteggere il ciclo di vita dell'evento.

#### Acceptance Criteria

1. WHEN Event_Service restituisce `status` uguale a `published`, THE Registration_Service SHALL considerare aperto l'evento — **REQ-REG-B03**.
2. IF Event_Service restituisce `status` diverso da `published` o omette `status`, THEN THE Registration_Service SHALL interrompere il POST e rispondere con stato HTTP `422` e Error_Response con codice `EVENT_NOT_OPEN` — **REQ-REG-B03**.

### Requirement 8: Doppia iscrizione — REQ-REG-B04

**User Story:** Come gestore, voglio impedire iscrizioni confermate duplicate, così da mantenere unica la partecipazione attiva.

#### Acceptance Criteria

1. IF esiste una Registration `confirmed` con la stessa coppia `user_id` ed `event_id`, THEN THE Registration_Service SHALL rispondere con stato HTTP `409` e Error_Response con codice `ALREADY_REGISTERED` — **REQ-REG-B04**.
2. WHEN per la coppia `user_id` ed `event_id` esistono solo Registration `cancelled`, THE Registration_Service SHALL consentire una nuova Registration `confirmed` dopo le altre validazioni — **REQ-REG-B04**.

### Requirement 9: Capienza massima — REQ-REG-B05

**User Story:** Come organizzatore, voglio rispettare la capienza dell'evento, così da non confermare partecipanti oltre il limite.

#### Acceptance Criteria

1. WHEN Registration_Service verifica la capienza, THE Registration_Service SHALL contare esclusivamente le Registration `confirmed` dell'evento — **REQ-REG-B05**.
2. IF il numero di Registration `confirmed` è maggiore o uguale a `event.capacity`, THEN THE Registration_Service SHALL rispondere con stato HTTP `409` e Error_Response con codice `EVENT_FULL` — **REQ-REG-B05**.
3. WHEN una Registration `confirmed` viene cancellata o eliminata, THE Registration_Service SHALL escludere Registration dai successivi conteggi di capienza — **REQ-REG-B05**.

### Requirement 10: Prezzo — REQ-REG-B06

**User Story:** Come partecipante, voglio registrare il prezzo dell'evento al momento dell'iscrizione, così da conservarne il valore storico.

#### Acceptance Criteria

1. WHEN Registration_Service crea Registration, THE Registration_Service SHALL copiare `amount` esclusivamente da `event.price` restituito da Event_Service — **REQ-REG-B06**.
2. WHEN Event_Service modifica successivamente `event.price`, THE Registration_Service SHALL mantenere invariato `amount` delle Registration esistenti — **REQ-REG-B06**.

### Requirement 11: Transizione di stato — REQ-REG-B07

**User Story:** Come partecipante, voglio cancellare un'iscrizione confermata senza riattivarla, così da avere un ciclo di vita deterministico.

#### Acceptance Criteria

1. WHEN Registration_Service crea Registration, THE Registration_Service SHALL assegnare `confirmed` a `status` — **REQ-REG-B07**.
2. WHEN un PATCH richiede la transizione `confirmed`→`cancelled`, THE Registration_Service SHALL modificare esclusivamente `status` e `updated_at` e rispondere con stato HTTP `200` — **REQ-REG-B07**.
3. IF un PATCH richiede un cambio di Registration_Status diverso da `confirmed`→`cancelled`, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `INVALID_STATUS_TRANSITION` — **REQ-REG-B07**.
4. WHEN un PATCH richiede lo stesso Registration_Status corrente, THE Registration_Service SHALL trattare la richiesta come idempotente, rispondere con stato HTTP `200` e mantenere invariati i campi diversi da `updated_at` — **REQ-REG-B07**.

### Requirement 12: Statistiche evento — REQ-REG-B08

**User Story:** Come organizzatore, voglio consultare capienza e disponibilità, così da monitorare le iscrizioni confermate.

#### Acceptance Criteria

1. WHEN Registration_Service riceve `GET /api/v1/registrations/stats` con `event_id` UUID, THE Registration_Service SHALL chiamare `GET {EVENT_SERVICE_URL}/api/v1/events/{event_id}` — **REQ-REG-B08**.
2. WHEN Event_Service restituisce l'evento, THE Registration_Service SHALL rispondere con stato HTTP `200` e JSON `event_id`, `capacity`, `confirmed` e `available`, dove `confirmed` conta solo le Registration `confirmed` e `available` vale `max(capacity-confirmed,0)` — **REQ-REG-B08**.
3. IF Event_Service risponde con stato HTTP `404` durante la richiesta stats, THEN THE Registration_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND` — **REQ-REG-B08**.
4. IF `event_id` è assente o non è un UUID, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR` — **REQ-REG-B08**.

### Requirement 13: Dipendenze non raggiungibili — REQ-REG-B09

**User Story:** Come client, voglio distinguere l'indisponibilità delle dipendenze, così da gestire un errore temporaneo.

#### Acceptance Criteria

1. WHEN Registration_Service carica la configurazione, THE Registration_Service SHALL usare esclusivamente `USER_SERVICE_URL` e `EVENT_SERVICE_URL`, con valori predefiniti `http://localhost:5001` e `http://localhost:5002` — **REQ-REG-B09**.
2. WHEN POST o stats effettua una chiamata a User_Service o Event_Service, THE Registration_Service SHALL applicare un timeout esatto di `2` secondi — **REQ-REG-B09**.
3. IF una chiamata esterna di POST o stats supera il timeout, subisce una connessione rifiutata o riceve uno stato HTTP `5xx`, THEN THE Registration_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE` — **REQ-REG-B09**.

### Requirement 14: Persistenza intercambiabile

**User Story:** Come sviluppatore, voglio cambiare backend tramite configurazione, così da preservare la logica applicativa.

#### Acceptance Criteria

1. WHEN `STORAGE_BACKEND` è omesso o vale `memory`, THE Registration_Service SHALL conservare le Registration in memoria senza creare file di dati.
2. WHEN `DATA_DIR` è omesso, THE Registration_Service SHALL usare `./data` come directory di persistenza.
3. WHEN `STORAGE_BACKEND` vale `json` o `sqlite` e la directory `DATA_DIR` non esiste, THE Registration_Service SHALL creare la directory configurata.
4. WHEN `STORAGE_BACKEND` vale `json`, THE Registration_Service SHALL persistere le Registration in un file in `DATA_DIR` usando esclusivamente la libreria standard `json`.
5. WHEN `STORAGE_BACKEND` vale `sqlite`, THE Registration_Service SHALL persistere le Registration in un file in `DATA_DIR` usando esclusivamente la libreria standard `sqlite3`.
6. WHEN Registration_Service accede alla persistenza, THE Registration_Service SHALL usare Repository senza richiedere modifiche alla logica di business o HTTP al cambio di backend.

### Requirement 15: Conformità del contratto e degli errori

**User Story:** Come client, voglio risposte conformi a un contratto stabile, così da integrare Registration_Service in modo deterministico.

#### Acceptance Criteria

1. WHEN Registration_Service invia o riceve un body, THE Registration_Service SHALL usare JSON con nomi di campo in `snake_case`.
2. WHEN Registration_Service restituisce Registration, THE Registration_Service SHALL rappresentare `amount` come numero EUR con due decimali, `status` come Registration_Status e i timestamp come ISO_8601_UTC.
3. WHEN Registration_Service restituisce una risposta, THE Registration_Service SHALL rispettare lo schema applicabile del Contratto_OpenAPI senza proprietà aggiuntive.
4. WHEN Registration_Service restituisce un errore, THE Registration_Service SHALL usare Error_Response con `code` in `UPPER_SNAKE`, `message` leggibile e `details` come oggetto JSON.
5. IF una validazione fallisce senza un codice di business specifico, THEN THE Registration_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
