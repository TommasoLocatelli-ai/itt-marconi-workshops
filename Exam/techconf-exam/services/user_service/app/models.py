"""Modello dati del user-service.

Definisce la dataclass :class:`User` (fonte di verità per la rappresentazione
di un utente all'interno del servizio) insieme alle costanti sui ruoli e a un
helper per i timestamp ISO 8601 UTC.

Il metodo :meth:`User.to_dict` produce un dizionario conforme allo schema
``User`` del contratto OpenAPI (``contracts/openapi/user-service.yaml``):
tutti i campi obbligatori sono sempre presenti, ``company`` è sempre presente
anche quando ``None`` (nullable ma non omesso), e non vengono aggiunti campi
extra (``additionalProperties: false``).

Requirements: REQ-USR-03, REQ-USR-13.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Ruoli ammessi per un utente e ruolo di default usato dal service layer.
ROLES = ("attendee", "speaker", "organizer")
DEFAULT_ROLE = "attendee"


def utc_now_iso() -> str:
    """Restituisce il timestamp corrente in ISO 8601 UTC con suffisso ``Z``.

    Il valore è privo di microsecondi, es. ``"2026-10-15T09:30:00Z"``.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class User:
    """Rappresentazione di un utente della piattaforma TechConf.

    Il campo ``email`` è sempre memorizzato in minuscolo (REQ-USR-B02) e i
    timestamp ``created_at``/``updated_at`` sono stringhe ISO 8601 UTC.
    """

    id: str
    first_name: str
    last_name: str
    email: str            # sempre lowercase
    role: str             # uno tra ROLES: 'attendee' | 'speaker' | 'organizer'
    created_at: str       # ISO 8601 UTC, es. "2026-10-15T09:30:00Z"
    updated_at: str       # ISO 8601 UTC
    company: Optional[str] = None

    def to_dict(self) -> dict:
        """Serializza l'utente in un dict conforme allo schema ``User``.

        Ordine dei campi: id, first_name, last_name, email, company, role,
        created_at, updated_at. Il campo ``company`` è sempre presente (anche
        quando ``None`` → ``null`` nel JSON).
        """
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "company": self.company,
            "role": self.role,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
