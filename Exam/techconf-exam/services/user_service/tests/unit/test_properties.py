"""Property-based test del user-service (Hypothesis).

Questo modulo copre le 11 **Correctness Properties** definite nel design
document (`.kiro/specs/user-service/design.md`). Ogni test è annotato con una
docstring nel formato `Feature: user-service, Property N: <testo>` per la
tracciabilità verso il design, e con un marker ``@pytest.mark.req(...)`` verso
i requisiti REQ-USR-*.

Approccio:

* Le Property 1–10 esercitano il **service layer** (:class:`UserService`) con un
  :class:`MemoryRepository` reale (nessun mock). Un service NUOVO viene creato
  all'inizio del corpo di ogni test, così Hypothesis non condivide stato tra un
  esempio e l'altro (fondamentale per non innescare falsi conflitti di email).
* La Property 11 confronta i tre backend (`memory`, `json`, `sqlite`) sulla
  stessa sequenza di operazioni; i backend su file usano directory temporanee
  create con ``tempfile.mkdtemp()`` e ripulite in ``finally`` con
  ``shutil.rmtree``.

Strategie Hypothesis
--------------------
* ``emails``  — genera email conformi al regex del service (``local@dominio.com``).
* ``names``   — nomi di 1–30 caratteri, non vuoti dopo ``strip`` (rispettano il
  vincolo 1–50 del service).
* ``roles``   — uno tra i ruoli ammessi.

Requirements: REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06, REQ-USR-07,
REQ-USR-08, REQ-USR-09, REQ-USR-10, REQ-USR-11, REQ-USR-12.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid

import pytest
from hypothesis import given, settings, strategies as st

from app.service import UserService
from app.repository import (
    MemoryRepository,
    JsonRepository,
    SqliteRepository,
)
from app.exceptions import EmailAlreadyExistsError, NotFoundError


# --------------------------------------------------------------------------- #
# Strategie
# --------------------------------------------------------------------------- #
# Email conforme al regex del service: ^[^@\s]+@[^@\s]+\.[^@\s]+$
emails = st.builds(
    lambda a, b: f"{a}@{b}.com",
    st.text("abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=10),
    st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
)

# Nomi: 1–30 caratteri, non vuoti dopo strip (rientrano nel vincolo 1–50).
names = st.text(
    st.characters(min_codepoint=65, max_codepoint=122),
    min_size=1,
    max_size=30,
).filter(lambda s: len(s.strip()) >= 1)

roles = st.sampled_from(["attendee", "speaker", "organizer"])

# Regex per validare il formato UUID v4 dell'id generato.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
# Regex per validare il formato timestamp ISO 8601 UTC (con suffisso Z).
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# --------------------------------------------------------------------------- #
# Property 1 — Creazione preserva i dati di input
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-03")
@given(first_name=names, last_name=names, email=emails, role=roles)
@settings(max_examples=50)
def test_create_preserves_input(first_name, last_name, email, role):
    """Feature: user-service, Property 1: Creazione preserva i dati di input."""
    svc = UserService(MemoryRepository())

    result = svc.create_user(
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": role,
        }
    )

    assert result["first_name"] == first_name
    assert result["last_name"] == last_name
    assert result["email"] == email.lower()
    assert result["role"] == role
    assert _UUID_RE.match(result["id"])
    assert _ISO_RE.match(result["created_at"])
    assert _ISO_RE.match(result["updated_at"])


# --------------------------------------------------------------------------- #
# Property 2 — Unicità email è invariante case-insensitive
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-09")
@given(email=emails)
@settings(max_examples=50)
def test_duplicate_email_always_rejected(email):
    """Feature: user-service, Property 2: Unicità email invariante case-insensitive."""
    svc = UserService(MemoryRepository())

    svc.create_user(
        {"first_name": "Ada", "last_name": "Byron", "email": email.lower()}
    )

    with pytest.raises(EmailAlreadyExistsError):
        svc.create_user(
            {"first_name": "Grace", "last_name": "Hopper", "email": email.upper()}
        )


# --------------------------------------------------------------------------- #
# Property 3 — Normalizzazione email è un'invariante di salvataggio
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-10")
@given(email=emails)
@settings(max_examples=50)
def test_email_always_stored_lowercase(email):
    """Feature: user-service, Property 3: Normalizzazione email invariante di salvataggio."""
    svc = UserService(MemoryRepository())

    result = svc.create_user(
        {"first_name": "Ada", "last_name": "Byron", "email": email.upper()}
    )

    assert result["email"] == email.lower()


# --------------------------------------------------------------------------- #
# Property 4 — Filtro per ruolo è completo e preciso
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-11")
@given(
    users=st.lists(
        st.tuples(emails, roles),
        min_size=1,
        max_size=15,
        unique_by=lambda t: t[0].lower(),  # email uniche → nessun 409
    ),
    target_role=roles,
)
@settings(max_examples=50)
def test_role_filter_is_complete_and_precise(users, target_role):
    """Feature: user-service, Property 4: Filtro per ruolo completo e preciso."""
    svc = UserService(MemoryRepository())

    expected = 0
    for email, role in users:
        svc.create_user(
            {"first_name": "N", "last_name": "S", "email": email, "role": role}
        )
        if role == target_role:
            expected += 1

    page = svc.list_users({"role": target_role}, page=1, page_size=100)

    assert all(u["role"] == target_role for u in page["items"])
    assert page["total"] == expected
    assert len(page["items"]) == expected


# --------------------------------------------------------------------------- #
# Property 5 — Filtro per email è completo e preciso (case-insensitive)
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-11")
@given(
    users=st.lists(
        emails,
        min_size=1,
        max_size=15,
        unique_by=lambda e: e.lower(),
    ),
    data=st.data(),
)
@settings(max_examples=50)
def test_email_filter_is_case_insensitive(users, data):
    """Feature: user-service, Property 5: Filtro per email completo e preciso (case-insensitive)."""
    svc = UserService(MemoryRepository())

    for email in users:
        svc.create_user({"first_name": "N", "last_name": "S", "email": email})

    # Scegli un'email esistente e alterala nella capitalizzazione.
    target = data.draw(st.sampled_from(users))
    query = target.upper()

    page = svc.list_users({"email": query}, page=1, page_size=100)

    assert all(u["email"] == target.lower() for u in page["items"])
    assert page["total"] == 1
    assert len(page["items"]) == 1


# --------------------------------------------------------------------------- #
# Property 6 — Filtri combinati applicano AND logico
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-11")
@given(
    users=st.lists(
        st.tuples(emails, roles),
        min_size=1,
        max_size=15,
        unique_by=lambda t: t[0].lower(),
    ),
    target_role=roles,
    data=st.data(),
)
@settings(max_examples=50)
def test_combined_filters_apply_and_logic(users, target_role, data):
    """Feature: user-service, Property 6: Filtri combinati applicano AND logico."""
    svc = UserService(MemoryRepository())

    for email, role in users:
        svc.create_user(
            {"first_name": "N", "last_name": "S", "email": email, "role": role}
        )

    target_email = data.draw(st.sampled_from([e for e, _ in users]))

    page = svc.list_users(
        {"role": target_role, "email": target_email},
        page=1,
        page_size=100,
    )

    for u in page["items"]:
        assert u["role"] == target_role
        assert u["email"] == target_email.lower()


# --------------------------------------------------------------------------- #
# Property 7 — Round-trip GET dopo creazione
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-05")
@given(first_name=names, last_name=names, email=emails, role=roles)
@settings(max_examples=50)
def test_get_after_create_roundtrip(first_name, last_name, email, role):
    """Feature: user-service, Property 7: Round-trip GET dopo creazione."""
    svc = UserService(MemoryRepository())

    created = svc.create_user(
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": role,
        }
    )

    fetched = svc.get_user(created["id"])

    assert fetched == created


# --------------------------------------------------------------------------- #
# Property 8 — PUT sostituisce integralmente i campi scrivibili
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-06")
@given(
    email1=emails,
    email2=emails,
    first_name=names,
    last_name=names,
    role=roles,
)
@settings(max_examples=50)
def test_put_replaces_writable_fields(email1, email2, first_name, last_name, role):
    """Feature: user-service, Property 8: PUT sostituisce integralmente i campi scrivibili."""
    svc = UserService(MemoryRepository())

    created = svc.create_user(
        {"first_name": "Old", "last_name": "Name", "email": email1, "role": "attendee"}
    )

    replaced = svc.replace_user(
        created["id"],
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email2,
            "role": role,
        },
    )

    # Nuovi valori applicati.
    assert replaced["first_name"] == first_name
    assert replaced["last_name"] == last_name
    assert replaced["email"] == email2.lower()
    assert replaced["role"] == role
    # id e created_at invariati.
    assert replaced["id"] == created["id"]
    assert replaced["created_at"] == created["created_at"]
    # updated_at non regredisce (timestamp con granularità al secondo).
    assert replaced["updated_at"] >= created["updated_at"]


# --------------------------------------------------------------------------- #
# Property 9 — PATCH aggiorna solo i campi presenti nel body
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-07")
@given(
    email=emails,
    new_first_name=names,
    field=st.sampled_from(["first_name", "last_name", "role"]),
)
@settings(max_examples=50)
def test_patch_updates_only_present_fields(email, new_first_name, field):
    """Feature: user-service, Property 9: PATCH aggiorna solo i campi presenti nel body."""
    svc = UserService(MemoryRepository())

    created = svc.create_user(
        {
            "first_name": "Original",
            "last_name": "Surname",
            "email": email,
            "role": "attendee",
            "company": "Acme",
        }
    )

    # Determina il valore nuovo per il singolo campo scelto.
    if field == "role":
        new_value = "speaker"
    else:
        new_value = new_first_name

    updated = svc.update_user(created["id"], {field: new_value})

    # Solo il campo scelto cambia; tutti gli altri restano identici (tranne
    # updated_at, che il service aggiorna sempre).
    for key in ("id", "first_name", "last_name", "email", "company", "role", "created_at"):
        if key == field:
            assert updated[key] == new_value
        else:
            assert updated[key] == created[key]

    assert updated["updated_at"] >= created["updated_at"]


# --------------------------------------------------------------------------- #
# Property 10 — DELETE rende l'utente irrecuperabile
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-08")
@given(email=emails, first_name=names, last_name=names)
@settings(max_examples=50)
def test_delete_makes_user_unreachable(email, first_name, last_name):
    """Feature: user-service, Property 10: DELETE rende l'utente irrecuperabile."""
    svc = UserService(MemoryRepository())

    created = svc.create_user(
        {"first_name": first_name, "last_name": last_name, "email": email}
    )

    svc.delete_user(created["id"])

    with pytest.raises(NotFoundError):
        svc.get_user(created["id"])


# --------------------------------------------------------------------------- #
# Property 11 — I tre backend producono risultati equivalenti
# --------------------------------------------------------------------------- #
def _make_user_dict(email: str, role: str, seq: int) -> dict:
    """Costruisce un user dict deterministico per il confronto tra backend."""
    ts = f"2026-01-01T00:00:{seq % 60:02d}Z"
    return {
        "id": str(uuid.UUID(int=seq)),  # id deterministico e univoco
        "first_name": "First",
        "last_name": "Last",
        "email": email.lower(),
        "company": None,
        "role": role,
        "created_at": ts,
        "updated_at": ts,
    }


@pytest.mark.req("REQ-USR-12")
@given(
    entries=st.lists(
        st.tuples(emails, roles),
        min_size=1,
        max_size=10,
        unique_by=lambda t: t[0].lower(),
    ),
    target_role=roles,
)
@settings(max_examples=50, deadline=None)
def test_backends_produce_equivalent_results(entries, target_role):
    """Feature: user-service, Property 11: I tre backend producono risultati equivalenti."""
    json_dir = tempfile.mkdtemp()
    sqlite_dir = tempfile.mkdtemp()
    try:
        backends = [
            MemoryRepository(),
            JsonRepository(data_dir=json_dir),
            SqliteRepository(data_dir=sqlite_dir),
        ]

        users = [
            _make_user_dict(email, role, seq)
            for seq, (email, role) in enumerate(entries, start=1)
        ]

        # Applica la stessa sequenza di save su tutti i backend.
        for repo in backends:
            for u in users:
                repo.save(u)

        # find_by_id equivalente per ogni utente salvato.
        for u in users:
            results = [repo.find_by_id(u["id"]) for repo in backends]
            assert all(r == results[0] for r in results)

        # find_all senza filtri: stesso insieme (ordine deterministico).
        all_results = [repo.find_all({}) for repo in backends]
        assert all(r == all_results[0] for r in all_results)

        # find_all con filtro role: stesso risultato.
        role_results = [repo.find_all({"role": target_role}) for repo in backends]
        assert all(r == role_results[0] for r in role_results)

        # email_exists equivalente per la prima email.
        first_email = users[0]["email"]
        exists_results = [repo.email_exists(first_email.upper()) for repo in backends]
        assert all(r is True for r in exists_results)

        # delete equivalente: rimuove il primo utente ovunque.
        deleted_results = [repo.delete(users[0]["id"]) for repo in backends]
        assert all(r is True for r in deleted_results)

        after_delete = [repo.find_by_id(users[0]["id"]) for repo in backends]
        assert all(r is None for r in after_delete)
    finally:
        shutil.rmtree(json_dir, ignore_errors=True)
        shutil.rmtree(sqlite_dir, ignore_errors=True)
