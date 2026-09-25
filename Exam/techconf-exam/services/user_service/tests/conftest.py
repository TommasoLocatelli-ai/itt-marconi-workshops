"""Fixture condivise per la suite di test del user-service.

Questo ``conftest.py`` prepara il ``sys.path`` e fornisce le fixture di base
usate dai test unitari:

* ``app``     — applicazione Flask isolata su :class:`MemoryRepository`.
* ``client``  — test client Flask basato su ``app``.
* ``repo``    — fixture parametrizzata sui tre backend (``memory``, ``json``,
  ``sqlite``); per ``json``/``sqlite`` usa ``tmp_path`` come ``data_dir`` così
  ogni test parte da uno storage pulito e isolato.
* ``make_user`` — factory (esposta sia come fixture sia come funzione
  importabile) per costruire ``user dict`` validi di test.

Sistemazione del ``sys.path``
-----------------------------
I path vengono calcolati relativamente a ``__file__``:

* la root del servizio (``services/user_service``) permette ``import app``;
* la root del repo (``techconf-exam``) permette
  ``from contracts.validator import assert_matches_contract``.

Requirements: REQ-USR-01, REQ-USR-12.
"""

import sys
import uuid
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Sistemazione del sys.path (calcolata relativamente a questo file)
# --------------------------------------------------------------------------- #
# __file__ = services/user_service/tests/conftest.py
#   parents[0] = tests
#   parents[1] = user_service   (root del servizio -> import app)
#   parents[2] = services
#   parents[3] = techconf-exam  (root del repo -> from contracts.validator ...)
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]

for _path in (str(_SERVICE_ROOT), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Import dopo la sistemazione del path: 'app' è ora importabile.
from app import create_app  # noqa: E402
from app.models import DEFAULT_ROLE, utc_now_iso  # noqa: E402
from app.repository import (  # noqa: E402
    JsonRepository,
    MemoryRepository,
    SqliteRepository,
)


# --------------------------------------------------------------------------- #
# Factory per user dict di test
# --------------------------------------------------------------------------- #
def make_user(**overrides) -> dict:
    """Costruisce un ``user dict`` valido, sovrascrivibile via ``overrides``.

    I default producono un utente coerente con lo schema ``User`` del
    contratto: ``id`` UUID v4, ``email`` in minuscolo, ``role`` di default e
    timestamp ISO 8601 UTC. Passare ``overrides`` per personalizzare i campi.
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
# Fixture
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_user_factory():
    """Espone :func:`make_user` come fixture (comoda nei test)."""
    return make_user


@pytest.fixture
def app():
    """Applicazione Flask isolata su un ``MemoryRepository`` pulito.

    Ogni test riceve una nuova app con uno storage in memoria vuoto, così i
    test restano indipendenti l'uno dall'altro.
    """
    return create_app(repo=MemoryRepository())


@pytest.fixture
def client(app):
    """Test client Flask basato sulla fixture ``app``."""
    return app.test_client()


@pytest.fixture(params=["memory", "json", "sqlite"])
def repo(request, tmp_path):
    """Repository parametrizzato sui tre backend supportati.

    * ``memory`` → :class:`MemoryRepository` (volatile, in-process).
    * ``json``   → :class:`JsonRepository` con ``data_dir=tmp_path``.
    * ``sqlite`` → :class:`SqliteRepository` con ``data_dir=tmp_path``.

    Per ``json``/``sqlite`` si passa direttamente ``data_dir`` invece di
    fare monkeypatch su ``config`` (le variabili module-level vengono lette
    all'import e il monkeypatch risulterebbe inaffidabile). ``tmp_path`` di
    pytest garantisce una directory pulita per ogni test.
    """
    backend = request.param
    if backend == "memory":
        return MemoryRepository()
    if backend == "json":
        return JsonRepository(data_dir=str(tmp_path))
    if backend == "sqlite":
        return SqliteRepository(data_dir=str(tmp_path))
    raise ValueError(f"Backend non supportato: {backend}")
