"""Test unitari del Service Layer (``app.service.UserService``).

Questa suite verifica la **logica di business** del servizio in isolamento dal
trasporto HTTP e — dove utile — dal dettaglio dello storage. Sono usate due
strategie complementari:

* :class:`~app.repository.MemoryRepository` reale, dove rende i test più chiari
  e verosimili (unicità email, normalizzazione, paginazione end-to-end).
* :class:`unittest.mock.MagicMock`, dove serve verificare **come** il service
  interagisce col repository (es. l'``exclude_id`` passato a ``email_exists`` o
  i ``filters`` passati a ``find_all``).

Regole di business coperte:

* **REQ-USR-B01** — unicità email case-insensitive (create/replace/update).
* **REQ-USR-B02** — normalizzazione email in minuscolo prima del salvataggio.
* **REQ-USR-B03** — filtri lista per ``role`` e/o ``email`` in AND logico.

Oltre alla validazione dei campi e alla gestione delle risorse assenti.

Requirements: REQ-USR-03..11.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from app.service import UserService
from app.repository import MemoryRepository
from app.models import DEFAULT_ROLE, utc_now_iso
from app.exceptions import (
    ValidationError,
    EmailAlreadyExistsError,
    NotFoundError,
)


# --------------------------------------------------------------------------- #
# Helper locali
# --------------------------------------------------------------------------- #
def make_user(**overrides) -> dict:
    """Costruisce un ``user dict`` valido, sovrascrivibile via ``overrides``."""
    now = utc_now_iso()
    user = {
        "id": str(uuid.uuid4()),
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada.lovelace@example.com",
        "company": "Analytical Engines",
        "role": DEFAULT_ROLE,
        "created_at": now,
        "updated_at": now,
    }
    user.update(overrides)
    return user


def make_service(repo=None) -> UserService:
    """Istanzia un :class:`UserService` su un repository reale in memoria."""
    return UserService(repo if repo is not None else MemoryRepository())


def valid_body(**overrides) -> dict:
    """Body di creazione valido (solo campi scrivibili), personalizzabile."""
    body = {
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace.hopper@example.com",
        "company": "US Navy",
        "role": "speaker",
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# REQ-USR-B01 — unicità email
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-B01")
def test_create_raises_email_exists_when_duplicate():
    """create_user solleva EmailAlreadyExistsError se email_exists → True."""
    repo = MagicMock()
    repo.email_exists.return_value = True
    service = UserService(repo)

    with pytest.raises(EmailAlreadyExistsError):
        service.create_user(valid_body())

    repo.email_exists.assert_called_once()
    # In creazione l'unicità va verificata senza escludere alcun utente.
    _, kwargs = repo.email_exists.call_args
    assert kwargs.get("exclude_id") is None
    repo.save.assert_not_called()


@pytest.mark.req("REQ-USR-B01")
def test_replace_checks_email_exclude_self():
    """replace_user verifica l'unicità email escludendo l'id corrente."""
    existing = make_user(email="old@example.com")
    repo = MagicMock()
    repo.find_by_id.return_value = existing
    repo.email_exists.return_value = False
    repo.save.side_effect = lambda u: u
    service = UserService(repo)

    service.replace_user(existing["id"], valid_body(email="new@example.com"))

    repo.email_exists.assert_called_once()
    _, kwargs = repo.email_exists.call_args
    assert kwargs.get("exclude_id") == existing["id"]


@pytest.mark.req("REQ-USR-B01")
def test_patch_email_duplicate_raises():
    """update_user con email già usata da un altro utente → 409."""
    repo = MemoryRepository()
    service = UserService(repo)

    first = service.create_user(valid_body(email="first@example.com"))
    second = service.create_user(
        valid_body(email="second@example.com", first_name="Alan")
    )

    with pytest.raises(EmailAlreadyExistsError):
        service.update_user(second["id"], {"email": "first@example.com"})

    # Il primo utente non deve essere stato toccato.
    assert service.get_user(first["id"])["email"] == "first@example.com"


# --------------------------------------------------------------------------- #
# REQ-USR-B02 — normalizzazione email in minuscolo
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-B02")
def test_create_normalizes_email_to_lowercase():
    """create con email in maiuscolo → risultato normalizzato in minuscolo."""
    service = make_service()
    result = service.create_user(valid_body(email="USER@EXAMPLE.COM"))
    assert result["email"] == "user@example.com"


@pytest.mark.req("REQ-USR-B02")
def test_replace_normalizes_email():
    """replace_user normalizza l'email in minuscolo prima del salvataggio."""
    service = make_service()
    created = service.create_user(valid_body(email="init@example.com"))

    result = service.replace_user(
        created["id"], valid_body(email="MixedCase@Example.Com")
    )
    assert result["email"] == "mixedcase@example.com"


@pytest.mark.req("REQ-USR-B02")
def test_patch_normalizes_email():
    """update_user normalizza l'email in minuscolo quando presente nel body."""
    service = make_service()
    created = service.create_user(valid_body(email="init@example.com"))

    result = service.update_user(created["id"], {"email": "PATCHED@EXAMPLE.COM"})
    assert result["email"] == "patched@example.com"


# --------------------------------------------------------------------------- #
# REQ-USR-B03 — filtri lista (role/email in AND, email case-insensitive)
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-B03")
def test_list_applies_role_filter():
    """list_users inoltra il filtro ``role`` a repo.find_all."""
    repo = MagicMock()
    repo.find_all.return_value = []
    service = UserService(repo)

    service.list_users({"role": "speaker"}, 1, 20)

    repo.find_all.assert_called_once()
    (passed_filters,), _ = repo.find_all.call_args
    assert passed_filters.get("role") == "speaker"


@pytest.mark.req("REQ-USR-B03")
def test_list_applies_email_filter_case_insensitive():
    """list_users normalizza l'email del filtro in minuscolo per find_all."""
    repo = MagicMock()
    repo.find_all.return_value = []
    service = UserService(repo)

    service.list_users({"email": "Someone@Example.COM"}, 1, 20)

    (passed_filters,), _ = repo.find_all.call_args
    assert passed_filters.get("email") == "someone@example.com"


@pytest.mark.req("REQ-USR-B03")
def test_list_pagination():
    """list_users applica lo slicing corretto e riporta il total filtrato."""
    repo = MemoryRepository()
    service = UserService(repo)

    # 5 utenti con created_at crescente per un ordinamento deterministico.
    for i in range(5):
        repo.save(
            make_user(
                email=f"user{i}@example.com",
                created_at=f"2026-01-01T00:00:0{i}Z",
            )
        )

    page1 = service.list_users({}, page=1, page_size=2)
    assert page1["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2
    assert page1["items"][0]["email"] == "user0@example.com"
    assert page1["items"][1]["email"] == "user1@example.com"

    page3 = service.list_users({}, page=3, page_size=2)
    # Ultima pagina parziale: rimane un solo elemento.
    assert page3["total"] == 5
    assert len(page3["items"]) == 1
    assert page3["items"][0]["email"] == "user4@example.com"


# --------------------------------------------------------------------------- #
# Validazione input
# --------------------------------------------------------------------------- #
def test_create_missing_first_name_raises_validation_error():
    """create senza ``first_name`` → ValidationError."""
    service = make_service()
    body = valid_body()
    del body["first_name"]
    with pytest.raises(ValidationError):
        service.create_user(body)


def test_create_invalid_email_raises():
    """create con email malformata → ValidationError."""
    service = make_service()
    with pytest.raises(ValidationError):
        service.create_user(valid_body(email="not-an-email"))


def test_create_invalid_role_raises():
    """create con ruolo non ammesso → ValidationError."""
    service = make_service()
    with pytest.raises(ValidationError):
        service.create_user(valid_body(role="superadmin"))


def test_create_rejects_id_in_body():
    """create con campo ``id`` nel body → ValidationError (id server-generated)."""
    service = make_service()
    with pytest.raises(ValidationError):
        service.create_user(valid_body(id="client-supplied-id"))


def test_get_user_absent_raises_not_found():
    """get_user su id inesistente → NotFoundError."""
    service = make_service()
    with pytest.raises(NotFoundError):
        service.get_user("nonexistent-id")


def test_delete_user_absent_raises_not_found():
    """delete_user su id inesistente → NotFoundError."""
    service = make_service()
    with pytest.raises(NotFoundError):
        service.delete_user("nonexistent-id")


def test_update_only_changes_present_fields():
    """update_user modifica solo i campi nel body, lasciando invariati gli altri."""
    service = make_service()
    created = service.create_user(
        valid_body(first_name="Grace", last_name="Hopper", company="US Navy")
    )

    updated = service.update_user(created["id"], {"first_name": "Gracie"})

    assert updated["first_name"] == "Gracie"
    # Campi non presenti nel body restano invariati.
    assert updated["last_name"] == created["last_name"]
    assert updated["email"] == created["email"]
    assert updated["company"] == created["company"]
    assert updated["role"] == created["role"]
    # id e created_at preservati; updated_at aggiornato (o comunque presente).
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
