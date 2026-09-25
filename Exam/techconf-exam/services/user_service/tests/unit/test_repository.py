"""Test unitari del layer Repository, parametrizzati sui tre backend.

Questo modulo verifica il comportamento CRUD e di filtro dei repository del
user-service usando la fixture ``repo`` definita in ``tests/conftest.py``, che
è parametrizzata sui tre backend supportati (``memory``, ``json``, ``sqlite``).
Ogni test viene quindi eseguito una volta per backend, garantendo l'equivalenza
funzionale tra le implementazioni.

Per l'indipendenza dall'import path viene definito un helper locale
:func:`make_user` che costruisce ``user dict`` validi (``id`` UUID v4, campi
coerenti con lo schema ``User`` e timestamp ISO 8601 UTC).

Requirements: REQ-USR-12.
"""

import uuid

import pytest

from app.models import DEFAULT_ROLE, utc_now_iso


# --------------------------------------------------------------------------- #
# Helper locale per costruire user dict validi
# --------------------------------------------------------------------------- #
def make_user(**overrides) -> dict:
    """Costruisce un ``user dict`` valido, sovrascrivibile via ``overrides``.

    I default producono un utente coerente con lo schema ``User``: ``id`` UUID
    v4, ``email`` in minuscolo, ``role`` di default e timestamp ISO 8601 UTC.
    """
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


# --------------------------------------------------------------------------- #
# CRUD di base
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-12")
def test_save_and_find_by_id(repo):
    """``save`` persiste l'utente e ``find_by_id`` restituisce lo stesso dict."""
    user = make_user()
    saved = repo.save(user)
    assert saved == user

    found = repo.find_by_id(user["id"])
    assert found == user


@pytest.mark.req("REQ-USR-12")
def test_find_by_id_absent_returns_none(repo):
    """``find_by_id`` di un id inesistente restituisce ``None``."""
    assert repo.find_by_id(str(uuid.uuid4())) is None


@pytest.mark.req("REQ-USR-12")
def test_find_all_no_filter(repo):
    """``find_all({})`` restituisce tutti gli utenti salvati."""
    users = [
        make_user(email=f"user{i}@example.com", created_at=f"2026-01-0{i}T00:00:00Z")
        for i in range(1, 4)
    ]
    for u in users:
        repo.save(u)

    result = repo.find_all({})
    assert len(result) == 3
    assert {u["id"] for u in result} == {u["id"] for u in users}


@pytest.mark.req("REQ-USR-12")
def test_delete_removes_user(repo):
    """``delete`` rimuove l'utente e restituisce ``True``; ``False`` se assente."""
    user = make_user()
    repo.save(user)

    assert repo.delete(user["id"]) is True
    assert repo.find_by_id(user["id"]) is None
    # Una seconda delete sullo stesso id (ora assente) restituisce False.
    assert repo.delete(user["id"]) is False
    # Delete di un id mai esistito restituisce False.
    assert repo.delete(str(uuid.uuid4())) is False


@pytest.mark.req("REQ-USR-12")
def test_email_exists_case_insensitive(repo):
    """``email_exists`` confronta case-insensitive ed esclude ``exclude_id``."""
    user = make_user(email="user@example.com")
    repo.save(user)

    # Match indipendente dal case.
    assert repo.email_exists("USER@EXAMPLE.COM") is True
    assert repo.email_exists("user@example.com") is True

    # Escludendo l'utente stesso non ci sono altri utenti con quell'email.
    assert repo.email_exists("USER@EXAMPLE.COM", exclude_id=user["id"]) is False

    # Un'email non registrata non esiste.
    assert repo.email_exists("nobody@example.com") is False


# --------------------------------------------------------------------------- #
# Filtri di find_all
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-12")
def test_find_all_with_role_filter(repo):
    """``find_all({"role": ...})`` restituisce solo gli utenti con quel ruolo."""
    attendee = make_user(email="a@example.com", role="attendee")
    speaker1 = make_user(email="s1@example.com", role="speaker")
    speaker2 = make_user(email="s2@example.com", role="speaker")
    for u in (attendee, speaker1, speaker2):
        repo.save(u)

    result = repo.find_all({"role": "speaker"})
    assert len(result) == 2
    assert all(u["role"] == "speaker" for u in result)
    assert {u["id"] for u in result} == {speaker1["id"], speaker2["id"]}


def test_find_all_with_email_filter(repo):
    """``find_all({"email": ...})`` filtra in modo case-insensitive."""
    target = make_user(email="match@example.com")
    other = make_user(email="other@example.com")
    for u in (target, other):
        repo.save(u)

    result = repo.find_all({"email": "MATCH@EXAMPLE.COM"})
    assert len(result) == 1
    assert result[0]["id"] == target["id"]


def test_find_all_combined_filters(repo):
    """I filtri ``role`` ed ``email`` vengono applicati in AND logico."""
    wanted = make_user(email="wanted@example.com", role="speaker")
    same_email_wrong_role = make_user(email="wanted@example.com", role="attendee")
    same_role_wrong_email = make_user(email="another@example.com", role="speaker")
    # Nota: gli id sono distinti; le email possono coincidere solo a livello di
    # storage in-repo (nessun vincolo UNIQUE nei backend memory/json).
    for u in (wanted, same_role_wrong_email):
        repo.save(u)

    result = repo.find_all({"role": "speaker", "email": "WANTED@example.com"})
    assert len(result) == 1
    assert result[0]["id"] == wanted["id"]
    # L'utente con stessa email ma ruolo diverso non deve comparire.
    assert same_email_wrong_role["id"] not in {u["id"] for u in result}


# --------------------------------------------------------------------------- #
# Update di un utente esistente
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-12")
def test_save_update_existing(repo):
    """Un secondo ``save`` con lo stesso id aggiorna senza duplicare."""
    user = make_user(company="Old Corp")
    repo.save(user)

    updated = dict(user)
    updated["company"] = "New Corp"
    updated["updated_at"] = "2026-12-31T23:59:59Z"
    repo.save(updated)

    found = repo.find_by_id(user["id"])
    assert found["company"] == "New Corp"
    assert found["updated_at"] == "2026-12-31T23:59:59Z"

    # Non deve essere stato creato un secondo record.
    assert len(repo.find_all({})) == 1
