"""Service layer del user-service.

Questo modulo contiene tutta la **logica di business** del servizio, isolata
sia dal trasporto HTTP (``routes.py``) sia dal dettaglio dello storage
(``repository.py``). La classe :class:`UserService` riceve un
:class:`app.repository.UserRepository` per *dependency injection* e implementa
il ciclo di vita completo di un utente.

Regole di business implementate:

* **REQ-USR-B01** — unicità email case-insensitive (create/replace/update).
* **REQ-USR-B02** — normalizzazione email in minuscolo prima del salvataggio.
* **REQ-USR-B03** — filtri lista per ``role`` e/o ``email`` in AND logico.

La validazione dei campi è centralizzata in helper privati riusabili, così che
``create_user`` e ``replace_user`` condividano esattamente gli stessi vincoli
(entrambi trattano tutti i campi come obbligatori), mentre ``update_user``
(PATCH) valida solo i campi effettivamente presenti nel body.

Il service layer NON conosce Flask e non costruisce oggetti Response: solleva
le eccezioni custom (``ValidationError``, ``EmailAlreadyExistsError``,
``NotFoundError``) che il router mappa ai rispettivi codici HTTP.

Requirements: REQ-USR-03 … REQ-USR-11, REQ-USR-B01, REQ-USR-B02, REQ-USR-B03.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from .models import User, ROLES, DEFAULT_ROLE, utc_now_iso
from .exceptions import (
    ValidationError,
    EmailAlreadyExistsError,
    NotFoundError,
)


# Regex email semplice: un carattere non-@/spazio, @, dominio, punto, TLD.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Vincoli di lunghezza dei campi testuali.
_NAME_MAX = 50
_COMPANY_MAX = 100


def _validate_name(data: dict, field: str) -> str:
    """Valida un campo nome obbligatorio (``first_name``/``last_name``).

    Vincoli: presente, stringa, 1–50 caratteri dopo ``strip`` (non vuoto).
    Restituisce il valore originale (non strippato) da salvare.
    """
    if field not in data or data[field] is None:
        raise ValidationError(f"Field '{field}' is required", field)
    value = data[field]
    if not isinstance(value, str):
        raise ValidationError(f"Field '{field}' must be a string", field)
    if len(value.strip()) < 1:
        raise ValidationError(f"Field '{field}' must not be empty", field)
    if len(value) > _NAME_MAX:
        raise ValidationError(
            f"Field '{field}' must be at most {_NAME_MAX} characters", field
        )
    return value


def _validate_email(data: dict) -> str:
    """Valida il campo ``email`` obbligatorio e lo restituisce in minuscolo.

    Vincoli: presente, stringa, conforme al regex email. La normalizzazione a
    minuscolo (REQ-USR-B02) avviene qui, così ogni chiamante riceve già il
    valore canonico.
    """
    if "email" not in data or data["email"] is None:
        raise ValidationError("Field 'email' is required", "email")
    value = data["email"]
    if not isinstance(value, str):
        raise ValidationError("Field 'email' must be a string", "email")
    if not _EMAIL_RE.match(value.strip()):
        raise ValidationError("Field 'email' is not a valid email address", "email")
    return value.strip().lower()


def _validate_company(data: dict) -> Optional[str]:
    """Valida il campo opzionale ``company`` (max 100 caratteri se presente)."""
    if "company" not in data or data["company"] is None:
        return None
    value = data["company"]
    if not isinstance(value, str):
        raise ValidationError("Field 'company' must be a string", "company")
    if len(value) > _COMPANY_MAX:
        raise ValidationError(
            f"Field 'company' must be at most {_COMPANY_MAX} characters", "company"
        )
    return value


def _validate_role(data: dict, *, default: bool = True) -> Optional[str]:
    """Valida il campo opzionale ``role``.

    Se assente: restituisce :data:`DEFAULT_ROLE` quando ``default`` è ``True``,
    altrimenti ``None`` (usato dal PATCH per non toccare il campo).
    Se presente: deve appartenere a :data:`ROLES`.
    """
    if "role" not in data or data["role"] is None:
        return DEFAULT_ROLE if default else None
    value = data["role"]
    if not isinstance(value, str) or value not in ROLES:
        raise ValidationError(
            f"Field 'role' must be one of {', '.join(ROLES)}", "role"
        )
    return value


def _reject_id_in_body(data: dict) -> None:
    """Rifiuta la presenza del campo ``id`` nel body (id server-generated)."""
    if "id" in data:
        raise ValidationError("Field 'id' is not accepted in the request body", "id")


class UserService:
    """Logica di business per il ciclo di vita degli utenti.

    Riceve un repository per dependency injection e non conosce né Flask né il
    backend concreto di persistenza.
    """

    def __init__(self, repo):
        self.repo = repo

    # ------------------------------------------------------------------ #
    # CREATE — REQ-USR-03, REQ-USR-09, REQ-USR-10, REQ-USR-B01, B02
    # ------------------------------------------------------------------ #
    def create_user(self, data: dict) -> dict:
        """Crea un nuovo utente a partire dal body validato.

        Passi: rifiuta ``id`` nel body, valida tutti i campi obbligatori,
        normalizza l'email (B02), applica il ruolo di default, verifica
        l'unicità dell'email (B01), genera ``id``/timestamp e persiste.
        """
        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        _reject_id_in_body(data)

        first_name = _validate_name(data, "first_name")
        last_name = _validate_name(data, "last_name")
        email = _validate_email(data)          # già in minuscolo (B02)
        company = _validate_company(data)
        role = _validate_role(data)            # default 'attendee'

        if self.repo.email_exists(email, exclude_id=None):   # B01
            raise EmailAlreadyExistsError(
                f"Email '{email}' is already registered"
            )

        now = utc_now_iso()
        user = User(
            id=str(uuid.uuid4()),
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            created_at=now,
            updated_at=now,
            company=company,
        )
        return self.repo.save(user.to_dict())

    # ------------------------------------------------------------------ #
    # LIST — REQ-USR-04, REQ-USR-11, REQ-USR-B03
    # ------------------------------------------------------------------ #
    def list_users(self, filters: dict, page: int, page_size: int) -> dict:
        """Restituisce una pagina di utenti applicando i filtri forniti.

        ``filters`` può contenere ``role`` e/o ``email`` (già validati dal
        router). L'email viene normalizzata a minuscolo per coerenza con lo
        storage. Il repository applica i filtri in AND logico (B03); ``total``
        riflette il numero di utenti filtrati (non il totale assoluto).
        """
        filters = dict(filters or {})
        if filters.get("email"):
            filters["email"] = filters["email"].lower()

        matched = self.repo.find_all(filters)
        total = len(matched)

        start = (page - 1) * page_size
        end = page * page_size
        items = matched[start:end]

        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    # ------------------------------------------------------------------ #
    # GET — REQ-USR-05
    # ------------------------------------------------------------------ #
    def get_user(self, id: str) -> dict:
        """Restituisce l'utente con quell'``id`` o solleva NotFoundError."""
        user = self.repo.find_by_id(id)
        if user is None:
            raise NotFoundError(f"User '{id}' not found")
        return user

    # ------------------------------------------------------------------ #
    # PUT (replace) — REQ-USR-06, REQ-USR-B01, B02
    # ------------------------------------------------------------------ #
    def replace_user(self, id: str, data: dict) -> dict:
        """Sostituisce integralmente i campi scrivibili di un utente esistente.

        Valida tutti i campi come in ``create_user`` (obbligatori), verifica
        l'unicità email escludendo l'utente corrente (B01), preserva ``id`` e
        ``created_at`` originali e aggiorna ``updated_at``.
        """
        existing = self.repo.find_by_id(id)
        if existing is None:
            raise NotFoundError(f"User '{id}' not found")

        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        _reject_id_in_body(data)

        first_name = _validate_name(data, "first_name")
        last_name = _validate_name(data, "last_name")
        email = _validate_email(data)          # già in minuscolo (B02)
        company = _validate_company(data)
        role = _validate_role(data)            # default 'attendee'

        if self.repo.email_exists(email, exclude_id=id):     # B01
            raise EmailAlreadyExistsError(
                f"Email '{email}' is already registered"
            )

        user = User(
            id=existing["id"],
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
            created_at=existing["created_at"],
            updated_at=utc_now_iso(),
            company=company,
        )
        return self.repo.save(user.to_dict())

    # ------------------------------------------------------------------ #
    # PATCH (partial update) — REQ-USR-07, REQ-USR-B01, B02
    # ------------------------------------------------------------------ #
    def update_user(self, id: str, data: dict) -> dict:
        """Aggiorna solo i campi presenti nel body di un utente esistente.

        Valida esclusivamente i campi forniti; normalizza l'email se presente
        (B02) e ne verifica l'unicità escludendo l'utente corrente (B01).
        Preserva ``id`` e ``created_at`` e aggiorna ``updated_at``.
        """
        existing = self.repo.find_by_id(id)
        if existing is None:
            raise NotFoundError(f"User '{id}' not found")

        if not isinstance(data, dict):
            raise ValidationError("Request body must be a JSON object")
        _reject_id_in_body(data)

        updated = dict(existing)

        if "first_name" in data:
            updated["first_name"] = _validate_name(data, "first_name")
        if "last_name" in data:
            updated["last_name"] = _validate_name(data, "last_name")
        if "email" in data:
            email = _validate_email(data)      # già in minuscolo (B02)
            if self.repo.email_exists(email, exclude_id=id):  # B01
                raise EmailAlreadyExistsError(
                    f"Email '{email}' is already registered"
                )
            updated["email"] = email
        if "company" in data:
            updated["company"] = _validate_company(data)
        if "role" in data:
            # default=False: se il valore è None viene comunque validato/rifiutato
            role = _validate_role(data, default=False)
            updated["role"] = role

        updated["updated_at"] = utc_now_iso()
        # id e created_at restano invariati (provengono da existing).
        return self.repo.save(updated)

    # ------------------------------------------------------------------ #
    # DELETE — REQ-USR-08
    # ------------------------------------------------------------------ #
    def delete_user(self, id: str) -> None:
        """Elimina un utente esistente; solleva NotFoundError se assente."""
        existing = self.repo.find_by_id(id)
        if existing is None:
            raise NotFoundError(f"User '{id}' not found")
        self.repo.delete(id)
