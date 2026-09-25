# TechConf — Product Overview

## Dominio

TechConf è una piattaforma a microservizi per la gestione delle iscrizioni a conferenze tecnologiche (cloud, AI, security). Il sistema consente a organizzatori, speaker e partecipanti di interagire attraverso un insieme di servizi indipendenti che comunicano via HTTP.

## Scopo del sistema

Gestire l'intero ciclo di vita di una conferenza tech: dalla registrazione degli utenti, alla pubblicazione degli eventi, alle iscrizioni dei partecipanti, fino alla raccolta dei feedback e all'invio di notifiche.

## Microservizi

| # | Servizio | Porta | Tipo | Responsabilità |
|---|---|---|---|---|
| 1 | **user-service** | 5001 | Obbligatorio | Anagrafica utenti della piattaforma (partecipanti, speaker, organizzatori) |
| 2 | **event-service** | 5002 | Obbligatorio | Conferenze con ciclo di vita (draft → published → cancelled) e gestione capienza |
| 3 | **registration-service** | 5003 | Obbligatorio | Iscrizioni degli utenti agli eventi pubblicati, con controllo capienza |
| 4 | **feedback-service** | 5004 | Opzionale | Valutazioni e commenti degli iscritti sugli eventi |
| 5 | **notification-service** | 5005 | Opzionale | Notifiche individuali e broadcast verso gli iscritti a un evento |

## Relazioni tra i servizi

```
user-service      ← chiamato da: event, registration, notification
event-service     → chiama: user  |  ← chiamato da: registration, feedback
registration-svc  → chiama: user, event  |  ← chiamato da: feedback, notification
feedback-service  → chiama: registration, event
notification-svc  → chiama: user, registration
```

## Risorse principali

- **User**: persona con ruolo `attendee | speaker | organizer`, email univoca
- **Event**: conferenza con venue, date, capienza e prezzo; ciclo di vita `draft → published → cancelled`
- **Registration**: iscrizione di un utente a un evento pubblicato; stato `confirmed | cancelled`; `amount` copiato da `event.price`
- **Feedback**: valutazione (rating 1–5) lasciata da un utente iscritto a un evento
- **Notification**: messaggio verso un utente via `email | sms | push`; stato `queued → sent | failed`

## Campi comuni a tutte le risorse

Ogni risorsa espone: `id` (UUID v4, generato dal server), `created_at` e `updated_at` (datetime ISO 8601 UTC, read-only).

## Utenti tipici

- **Organizzatore**: crea e pubblica conferenze
- **Partecipante (attendee)**: si iscrive agli eventi pubblicati, lascia feedback
- **Speaker**: tiene sessioni agli eventi; può iscriversi come partecipante
