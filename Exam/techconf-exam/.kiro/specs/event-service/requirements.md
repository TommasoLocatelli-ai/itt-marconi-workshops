# Requirements Document

## Introduction

L'**event-service** gestisce le conferenze della piattaforma TechConf e il relativo ciclo di vita. Il servizio espone API REST sotto il base path `/api/v1/events`, usa la porta di sviluppo `5002` configurata tramite la variabile d'ambiente `PORT` e verifica gli organizzatori mediante chiamate HTTP al user-service.

Il contratto HTTP definitivo è `contracts/openapi/event-service.yaml`, che costituisce la fonte di verità non modificabile per endpoint, schemi, parametri e risposte. Il presente documento definisce inoltre le regole di business tracciabili `REQ-EVT-B01`–`REQ-EVT-B06`, gli standard di configurazione, la persistenza intercambiabile e la conformità delle risposte.

## Glossary

| Termine | Definizione |
|---|---|
| **Event_Service** | Il microservizio oggetto del presente documento, identificato nelle risposte di health check come `event-service`. |
| **Event** | La risorsa che rappresenta una conferenza TechConf. |
| **User_Service** | Il microservizio interrogato da Event_Service per verificare l'esistenza e il ruolo dell'organizzatore. |
| **Organizer** | Un utente restituito da User_Service con campo `role` uguale a `organizer`. |
| **Event_Status** | Lo stato del ciclo di vita di Event: `draft`, `published` oppure `cancelled`. |
| **Campo_obbligatorio** | Un campo che deve essere presente in un body di creazione o sostituzione completa: `title`, `organizer_id`, `venue`, `city`, `start_date`, `end_date`, `capacity` e `price`. |
| **Campo_read_only** | Un campo generato da Event_Service e restituito ai client, ma non accettato in input: `id`, `created_at` oppure `updated_at`. |
| **UUID_v4** | Identificativo univoco universale versione 4 generato da Event_Service. |
| **ISO_8601_UTC** | Formato timestamp UTC `YYYY-MM-DDTHH:MM:SSZ` usato per `created_at` e `updated_at`. |
| **Data_Evento** | Data di calendario nel formato `YYYY-MM-DD`. |
| **Sostituzione_Completa** | Operazione PUT che richiede tutti i Campi_obbligatori e sostituisce i dati scrivibili di Event secondo i valori ricevuti. |
| **Aggiornamento_Parziale** | Operazione PATCH che modifica esclusivamente i campi presenti nel body. |
| **Transizione_di_Stato** | Modifica di Event_Status da un valore a un valore diverso; la richiesta dello stesso valore non costituisce una Transizione_di_Stato. |
| **Paginazione** | Suddivisione della lista mediante `page` e `page_size`, con risposta composta da `items`, `page`, `page_size` e `total`. |
| **Confronto_Città** | Confronto esatto case-insensitive tra il filtro `city` e il campo `city`, senza corrispondenze parziali. |
| **PORT** | Variabile d'ambiente che determina la porta di ascolto di Event_Service. |
| **USER_SERVICE_URL** | Variabile d'ambiente contenente l'URL base di User_Service, con valore predefinito `http://localhost:5001`. |
| **STORAGE_BACKEND** | Variabile d'ambiente che seleziona il backend di persistenza: `memory`, `json` oppure `sqlite`; il valore predefinito è `memory`. |
| **DATA_DIR** | Variabile d'ambiente che indica la directory dei file di persistenza, con valore predefinito `./data`. |
| **Router** | Livello responsabile dell'input e dell'output HTTP, inclusi parsing, validazione HTTP e costruzione delle risposte. |
| **Service_Layer** | Livello responsabile delle regole di business `REQ-EVT-B01`–`REQ-EVT-B06`. |
| **Repository** | Livello che espone operazioni di persistenza indipendenti dal backend a Service_Layer. |
| **Error_Response** | Corpo JSON `{"error":{"code":"UPPER_SNAKE","message":"...","details":{}}}` usato per gli errori. |
| **Contratto_OpenAPI** | Il file non modificabile `contracts/openapi/event-service.yaml`. |

## Requirements

### Requirement 1: Infrastruttura e configurazione

**User Story:** Come operatore della piattaforma TechConf, voglio configurare Event_Service tramite variabili d'ambiente, così da eseguire il servizio in ambienti diversi senza modificare il codice sorgente.

#### Acceptance Criteria

1. WHEN Event_Service viene avviato, THE Event_Service SHALL leggere la porta di ascolto esclusivamente dalla variabile d'ambiente `PORT`.
2. WHEN l'ambiente di sviluppo configura `PORT` con il valore `5002`, THE Event_Service SHALL ascoltare sulla porta `5002`.
3. WHEN Event_Service viene avviato senza `USER_SERVICE_URL`, THE Event_Service SHALL usare `http://localhost:5001` come URL base di User_Service.
4. WHEN Event_Service viene avviato con `USER_SERVICE_URL`, THE Event_Service SHALL usare il valore di `USER_SERVICE_URL` come unico URL base di User_Service.
5. WHEN Event_Service viene avviato senza `STORAGE_BACKEND`, THE Event_Service SHALL selezionare il backend `memory`.
6. WHEN Event_Service viene avviato senza `DATA_DIR`, THE Event_Service SHALL usare `./data` come directory dei file di persistenza.
7. IF `STORAGE_BACKEND` contiene un valore diverso da `memory`, `json` e `sqlite`, THEN THE Event_Service SHALL selezionare il backend `memory`.
8. WHEN Event_Service carica la configurazione, THE Event_Service SHALL acquisire `PORT`, `USER_SERVICE_URL`, `STORAGE_BACKEND` e `DATA_DIR` dall'ambiente tramite un unico componente di configurazione.

### Requirement 2: Health check

**User Story:** Come orchestratore della piattaforma, voglio interrogare lo stato di Event_Service, così da verificare che il servizio sia raggiungibile.

#### Acceptance Criteria

1. WHEN Event_Service riceve `GET /health`, THE Event_Service SHALL rispondere con stato HTTP `200` e corpo JSON `{"status":"ok","service":"event-service"}`.
2. WHEN Event_Service genera la risposta di `GET /health`, THE Event_Service SHALL includere esclusivamente i campi obbligatori `status` e `service` definiti dallo schema `Health` del Contratto_OpenAPI.

### Requirement 3: Modello Event e validazione dei campi

**User Story:** Come client della piattaforma, voglio inviare dati Event con vincoli deterministici, così da ottenere risorse valide e coerenti.

#### Acceptance Criteria

1. IF un body POST o PUT omette almeno un Campo_obbligatorio, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
2. IF `title` non è una stringa con lunghezza compresa tra 3 e 120 caratteri, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
3. WHEN `description` è omesso oppure vale `null` in un body POST o PUT altrimenti valido, THE Event_Service SHALL rappresentare `description` con valore `null` nella risorsa risultante.
4. IF `description` è diverso da `null` e non è una stringa di lunghezza massima pari a 2000 caratteri, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
5. IF `organizer_id` non è una stringa in formato UUID, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
6. IF `venue` non è una stringa di lunghezza massima pari a 100 caratteri, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
7. IF `city` non è una stringa di lunghezza massima pari a 60 caratteri, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
8. IF `start_date` o `end_date` non è una Data_Evento valida, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
9. IF `capacity` non è un intero compreso tra 1 e 10000, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
10. IF `price` non è un numero maggiore o uguale a `0.00`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
11. IF `price` contiene più di due cifre decimali, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
12. IF `status` è presente e non appartiene a Event_Status, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
13. IF un body POST, PUT o PATCH contiene un campo non definito dal relativo schema del Contratto_OpenAPI, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
14. IF un body POST, PUT o PATCH contiene un Campo_read_only, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
15. WHEN Event_Service crea Event, THE Event_Service SHALL generare `id` come UUID_v4 e `created_at` e `updated_at` come timestamp ISO_8601_UTC.

### Requirement 4: Creazione di Event con POST

**User Story:** Come client della piattaforma, voglio creare una conferenza, così da gestire una nuova iniziativa TechConf.

#### Acceptance Criteria

1. WHEN Event_Service riceve `POST /api/v1/events` con un body valido e un Organizer valido, THE Event_Service SHALL creare Event e rispondere con stato HTTP `201` e la risorsa creata.
2. WHEN Event_Service crea Event senza il campo `status`, THE Event_Service SHALL assegnare `draft` al campo `status`.
3. WHEN Event_Service crea Event con successo, THE Event_Service SHALL includere l'header `Location` con valore `/api/v1/events/{id}`.
4. WHEN Event_Service crea Event con successo, THE Event_Service SHALL impostare `created_at` e `updated_at` al timestamp UTC corrente.
5. IF il body di `POST /api/v1/events` contiene JSON malformato, THEN THE Event_Service SHALL rispondere con stato HTTP `400` e Error_Response con codice `MALFORMED_JSON`.
6. IF il body di `POST /api/v1/events` viola un vincolo dello schema `EventCreate`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.

### Requirement 5: Lista, paginazione e parametri di ricerca

**User Story:** Come client della piattaforma, voglio consultare una lista paginata di conferenze, così da navigare un insieme di risultati di dimensione controllata.

#### Acceptance Criteria

1. WHEN Event_Service riceve `GET /api/v1/events` con parametri validi, THE Event_Service SHALL rispondere con stato HTTP `200` e corpo JSON contenente `items`, `page`, `page_size` e `total`.
2. WHEN il parametro `page` è omesso, THE Event_Service SHALL usare `1` come valore di `page`.
3. WHEN il parametro `page_size` è omesso, THE Event_Service SHALL usare `20` come valore di `page_size`.
4. IF `page` non è un intero maggiore o uguale a `1`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
5. IF `page_size` non è un intero compreso tra `1` e `100`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
6. IF il filtro `status` non appartiene a Event_Status, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
7. IF il filtro `city` non è una stringa, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
8. WHILE nessun Event soddisfa i filtri applicati, THE Event_Service SHALL rispondere con stato HTTP `200`, `items` uguale a `[]` e `total` uguale a `0`.
9. WHEN la pagina richiesta non contiene Event e almeno un Event soddisfa i filtri in altre pagine, THE Event_Service SHALL rispondere con stato HTTP `200`, `items` uguale a `[]` e `total` uguale al numero complessivo di Event filtrati.

### Requirement 6: Lettura di un singolo Event

**User Story:** Come client della piattaforma, voglio recuperare una conferenza tramite identificativo, così da consultarne tutti i dati.

#### Acceptance Criteria

1. WHEN Event_Service riceve `GET /api/v1/events/{id}` per un Event esistente, THE Event_Service SHALL rispondere con stato HTTP `200` e la risorsa Event completa.
2. IF Event_Service riceve `GET /api/v1/events/{id}` per un Event inesistente, THEN THE Event_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
3. WHEN Event_Service restituisce un singolo Event, THE Event_Service SHALL includere i campi `id`, `title`, `description`, `organizer_id`, `venue`, `city`, `start_date`, `end_date`, `capacity`, `price`, `status`, `created_at` e `updated_at` previsti dal Contratto_OpenAPI.

### Requirement 7: Sostituzione completa con PUT

**User Story:** Come client della piattaforma, voglio sostituire i dati scrivibili di una conferenza esistente, così da aggiornare la rappresentazione completa della conferenza.

#### Acceptance Criteria

1. WHEN Event_Service riceve `PUT /api/v1/events/{id}` per un Event esistente con tutti i Campi_obbligatori validi, THE Event_Service SHALL eseguire la Sostituzione_Completa e rispondere con stato HTTP `200` e la risorsa aggiornata.
2. WHEN Event_Service completa una Sostituzione_Completa, THE Event_Service SHALL mantenere invariati `id` e `created_at`.
3. WHEN Event_Service completa una Sostituzione_Completa, THE Event_Service SHALL impostare `updated_at` al timestamp UTC corrente.
4. WHEN un body PUT valido omette `description`, THE Event_Service SHALL impostare `description` a `null`.
5. WHEN un body PUT valido omette `status`, THE Event_Service SHALL mantenere Event_Status corrente.
6. WHEN Event_Service elabora un body PUT valido per un Event esistente, THE Event_Service SHALL validare sempre `organizer_id` tramite User_Service.
7. IF Event_Service riceve `PUT /api/v1/events/{id}` per un Event inesistente, THEN THE Event_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
8. IF il body PUT contiene JSON malformato, THEN THE Event_Service SHALL rispondere con stato HTTP `400` e Error_Response con codice `MALFORMED_JSON`.
9. IF il body PUT viola un vincolo dello schema `EventCreate` o una regola di business, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`, `INVALID_ORGANIZER` oppure `INVALID_STATUS_TRANSITION` secondo la condizione definita dal requisito violato.
10. IF la validazione obbligatoria di User_Service fallisce per indisponibilità della dipendenza, THEN THE Event_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE`.

### Requirement 8: Aggiornamento parziale con PATCH

**User Story:** Come client della piattaforma, voglio modificare solo i campi selezionati di una conferenza, così da preservare i dati non inclusi nella richiesta.

#### Acceptance Criteria

1. WHEN Event_Service riceve `PATCH /api/v1/events/{id}` con un oggetto JSON valido per un Event esistente, THE Event_Service SHALL eseguire l'Aggiornamento_Parziale e rispondere con stato HTTP `200` e la risorsa aggiornata.
2. WHEN Event_Service completa un Aggiornamento_Parziale, THE Event_Service SHALL mantenere invariati `id` e `created_at`.
3. WHEN Event_Service completa un Aggiornamento_Parziale, THE Event_Service SHALL impostare `updated_at` al timestamp UTC corrente.
4. WHEN un campo scrivibile è assente dal body PATCH, THE Event_Service SHALL mantenere invariato il valore corrente del campo assente.
5. WHEN il body PATCH omette `organizer_id`, THE Event_Service SHALL completare la richiesta senza chiamare User_Service per validare l'organizzatore.
6. WHEN il body PATCH contiene un `organizer_id` diverso dal valore corrente, THE Event_Service SHALL validare il nuovo `organizer_id` tramite User_Service.
7. WHEN il body PATCH contiene un `organizer_id` uguale al valore corrente, THE Event_Service SHALL mantenere l'organizzatore senza chiamare User_Service.
8. IF Event_Service riceve `PATCH /api/v1/events/{id}` per un Event inesistente, THEN THE Event_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
9. IF il body PATCH contiene JSON malformato, THEN THE Event_Service SHALL rispondere con stato HTTP `400` e Error_Response con codice `MALFORMED_JSON`.
10. IF il body PATCH viola un vincolo dello schema `EventUpdate` o una regola di business, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`, `REFERENCE_NOT_FOUND`, `INVALID_ORGANIZER` oppure `INVALID_STATUS_TRANSITION` secondo la condizione definita dal requisito violato.
11. IF la validazione richiesta di User_Service fallisce per indisponibilità della dipendenza, THEN THE Event_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE`.

### Requirement 9: Eliminazione di Event

**User Story:** Come amministratore della piattaforma, voglio eliminare una conferenza tramite identificativo, così da rimuovere una risorsa non più necessaria.

#### Acceptance Criteria

1. WHEN Event_Service riceve `DELETE /api/v1/events/{id}` per un Event esistente, THE Event_Service SHALL eliminare Event e rispondere con stato HTTP `204` senza body.
2. IF Event_Service riceve `DELETE /api/v1/events/{id}` per un Event inesistente, THEN THE Event_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.

### Requirement 10: Esistenza dell'organizzatore — REQ-EVT-B01

**User Story:** Come gestore della piattaforma, voglio associare ogni conferenza a un utente esistente, così da evitare riferimenti a identità inesistenti.

#### Acceptance Criteria

1. WHEN Event_Service valida `organizer_id`, THE Event_Service SHALL chiamare `GET {USER_SERVICE_URL}/api/v1/users/{organizer_id}` — **REQ-EVT-B01**.
2. WHEN un body POST supera la validazione locale, THE Event_Service SHALL validare sempre `organizer_id` tramite User_Service prima di creare Event — **REQ-EVT-B01**.
3. WHEN un body PUT per un Event esistente supera la validazione locale, THE Event_Service SHALL validare sempre `organizer_id` tramite User_Service prima di sostituire Event — **REQ-EVT-B01**.
4. WHEN un body PATCH per un Event esistente introduce un `organizer_id` diverso dal valore corrente, THE Event_Service SHALL validare il nuovo `organizer_id` tramite User_Service prima di aggiornare Event — **REQ-EVT-B01**.
5. IF User_Service risponde con stato HTTP `404`, THEN THE Event_Service SHALL interrompere l'operazione e rispondere con stato HTTP `422` e Error_Response con codice `REFERENCE_NOT_FOUND` — **REQ-EVT-B01**.
6. WHEN User_Service risponde con stato HTTP `200`, THE Event_Service SHALL verificare il campo `role` della risorsa utente prima di completare l'operazione — **REQ-EVT-B01**.

### Requirement 11: Ruolo dell'organizzatore — REQ-EVT-B02

**User Story:** Come gestore della piattaforma, voglio associare le conferenze esclusivamente a utenti organizzatori, così da rispettare le responsabilità definite dai ruoli TechConf.

#### Acceptance Criteria

1. WHEN User_Service restituisce un utente con `role` uguale a `organizer`, THE Event_Service SHALL considerare soddisfatta la validazione del ruolo — **REQ-EVT-B02**.
2. IF User_Service restituisce un utente con `role` diverso da `organizer` oppure senza il campo `role`, THEN THE Event_Service SHALL interrompere l'operazione e rispondere con stato HTTP `422` e Error_Response con codice `INVALID_ORGANIZER` — **REQ-EVT-B02**.

### Requirement 12: Coerenza delle date — REQ-EVT-B03

**User Story:** Come partecipante, voglio che la data finale di una conferenza sia coerente con la data iniziale, così da consultare un intervallo temporale valido.

#### Acceptance Criteria

1. WHEN `end_date` è successiva o uguale a `start_date`, THE Event_Service SHALL considerare soddisfatta la regola di coerenza delle date — **REQ-EVT-B03**.
2. IF `end_date` è precedente a `start_date`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR` — **REQ-EVT-B03**.
3. WHEN un body PATCH modifica `start_date` oppure `end_date`, THE Event_Service SHALL applicare la regola di coerenza alla coppia di date risultante dall'Aggiornamento_Parziale — **REQ-EVT-B03**.

### Requirement 13: Transizioni del ciclo di vita — REQ-EVT-B04

**User Story:** Come organizzatore, voglio modificare lo stato di una conferenza soltanto secondo transizioni definite, così da preservare la coerenza del ciclo di vita.

#### Acceptance Criteria

1. WHEN Event_Status cambia da `draft` a `published`, THE Event_Service SHALL accettare la Transizione_di_Stato — **REQ-EVT-B04**.
2. WHEN Event_Status cambia da `draft` a `cancelled`, THE Event_Service SHALL accettare la Transizione_di_Stato — **REQ-EVT-B04**.
3. WHEN Event_Status cambia da `published` a `cancelled`, THE Event_Service SHALL accettare la Transizione_di_Stato — **REQ-EVT-B04**.
4. IF un aggiornamento richiede una modifica di Event_Status diversa dalle transizioni `draft`→`published`, `draft`→`cancelled` e `published`→`cancelled`, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `INVALID_STATUS_TRANSITION` — **REQ-EVT-B04**.
5. WHEN un aggiornamento richiede Event_Status uguale al valore corrente, THE Event_Service SHALL trattare lo stato richiesto come aggiornamento idempotente e non come Transizione_di_Stato — **REQ-EVT-B04**.

### Requirement 14: Indisponibilità di User_Service — REQ-EVT-B05

**User Story:** Come client della piattaforma, voglio ricevere un errore distinguibile quando User_Service non è disponibile, così da poter gestire un errore temporaneo della dipendenza.

#### Acceptance Criteria

1. WHEN Event_Service avvia una chiamata HTTP a User_Service, THE Event_Service SHALL applicare un timeout esatto di 2 secondi — **REQ-EVT-B05**.
2. IF una chiamata a User_Service supera il timeout di 2 secondi, THEN THE Event_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE` — **REQ-EVT-B05**.
3. IF una chiamata a User_Service fallisce per connessione rifiutata o host non raggiungibile, THEN THE Event_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE` — **REQ-EVT-B05**.
4. IF User_Service risponde con uno stato HTTP `5xx`, THEN THE Event_Service SHALL rispondere con stato HTTP `503` e Error_Response con codice `DEPENDENCY_UNAVAILABLE` — **REQ-EVT-B05**.

### Requirement 15: Filtri di lista — REQ-EVT-B06

**User Story:** Come client della piattaforma, voglio filtrare le conferenze per stato e città, così da ottenere solo i risultati pertinenti.

#### Acceptance Criteria

1. WHEN `status` è presente nella query di lista, THE Event_Service SHALL includere esclusivamente Event con Event_Status uguale al valore richiesto — **REQ-EVT-B06**.
2. WHEN `city` è presente nella query di lista, THE Event_Service SHALL includere esclusivamente Event che soddisfano il Confronto_Città — **REQ-EVT-B06**.
3. WHEN `status` e `city` sono entrambi presenti nella query di lista, THE Event_Service SHALL applicare i due filtri mediante AND logico — **REQ-EVT-B06**.
4. WHEN Event_Service calcola `total`, THE Event_Service SHALL contare gli Event dopo l'applicazione di tutti i filtri e prima dell'applicazione della Paginazione — **REQ-EVT-B06**.
5. WHEN Event_Service costruisce `items`, THE Event_Service SHALL applicare la Paginazione all'insieme risultante dai filtri — **REQ-EVT-B06**.

### Requirement 16: Persistenza intercambiabile

**User Story:** Come sviluppatore, voglio cambiare il backend di persistenza tramite configurazione, così da usare memoria, JSON o SQLite senza modificare la logica di business o il livello HTTP.

#### Acceptance Criteria

1. WHEN `STORAGE_BACKEND` vale `memory`, THE Event_Service SHALL mantenere gli Event in memoria senza creare file di dati.
2. WHEN `STORAGE_BACKEND` vale `json`, THE Event_Service SHALL persistere gli Event in un file JSON collocato in `DATA_DIR` usando esclusivamente la libreria standard `json`.
3. WHEN `STORAGE_BACKEND` vale `sqlite`, THE Event_Service SHALL persistere gli Event in un file SQLite collocato in `DATA_DIR` usando esclusivamente la libreria standard `sqlite3`.
4. WHEN `STORAGE_BACKEND` cambia tra `memory`, `json` e `sqlite`, THE Event_Service SHALL mantenere invariati i contratti usati da Service_Layer e Router.
5. WHEN Service_Layer accede agli Event persistiti, THE Event_Service SHALL instradare le operazioni attraverso Repository.
6. WHEN Router gestisce una richiesta HTTP, THE Event_Service SHALL impedire l'accesso diretto di Router al backend di persistenza mediante Repository.
7. WHEN Event_Service usa il backend `json` o `sqlite`, THE Event_Service SHALL creare `DATA_DIR` qualora la directory configurata non esista.

### Requirement 17: Conformità OpenAPI, formati ed errori

**User Story:** Come client della piattaforma, voglio ricevere risposte conformi a un contratto stabile, così da integrare Event_Service in modo deterministico.

#### Acceptance Criteria

1. WHEN Event_Service restituisce una risposta con body, THE Event_Service SHALL usare il formato JSON e il `Content-Type: application/json`.
2. WHEN Event_Service restituisce dati JSON, THE Event_Service SHALL usare nomi di campo in `snake_case`.
3. WHEN Event_Service restituisce `created_at` o `updated_at`, THE Event_Service SHALL formattare il timestamp come ISO_8601_UTC.
4. WHEN Event_Service restituisce `price`, THE Event_Service SHALL rappresentare l'importo come numero EUR non negativo con precisione di due cifre decimali.
5. WHEN Event_Service restituisce un errore, THE Event_Service SHALL usare Error_Response con `code` in formato `UPPER_SNAKE`, `message` leggibile e `details` come oggetto JSON.
6. WHEN Event_Service restituisce una risposta definita dal Contratto_OpenAPI, THE Event_Service SHALL includere esclusivamente i campi ammessi dallo schema applicabile con `additionalProperties: false`.
7. WHEN Event_Service gestisce un endpoint, THE Event_Service SHALL rispettare i metodi, i parametri, gli stati HTTP e gli schemi definiti dal Contratto_OpenAPI.
8. IF una validazione di campo fallisce senza un codice di business più specifico, THEN THE Event_Service SHALL rispondere con stato HTTP `422` e Error_Response con codice `VALIDATION_ERROR`.
9. IF un identificativo Event non corrisponde a una risorsa esistente, THEN THE Event_Service SHALL rispondere con stato HTTP `404` e Error_Response con codice `NOT_FOUND`.
