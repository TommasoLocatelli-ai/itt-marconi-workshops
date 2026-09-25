"""Test unitari del livello HTTP (router Flask) del user-service.

Ogni endpoint è verificato con almeno un caso positivo (happy path) e i
principali casi di errore. Per ogni endpoint viene inoltre eseguita almeno
una validazione del contratto OpenAPI tramite
:func:`contracts.validator.assert_matches_contract`.

Il ``conftest.py`` della suite:

* sistema ``sys.path`` in modo che ``from contracts.validator import
  assert_matches_contract`` funzioni senza ulteriori accorgimenti;
* fornisce la fixture ``client`` (Flask test client su ``create_app`` con
  :class:`MemoryRepository`, storage pulito per ogni test);
* espone la factory ``make_user`` per costruire user dict di test.

Il validator accetta un oggetto ``requests.Response``-like oppure un semplice
``dict`` con chiavi ``status_code`` / ``headers`` / ``json``. La risposta del
Flask test client espone ``status_code`` e ``get_json()`` ma non ``json()``,
quindi la si adatta con :func:`_contract_response`.

Requirements: REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06,
REQ-USR-07, REQ-USR-08, REQ-USR-13.
"""

import pytest

from contracts.validator import assert_matches_contract


# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #
def _contract_response(resp) -> dict:
    """Adatta la risposta del Flask test client al formato del validator.

    Il validator accetta un dict ``{"status_code", "headers", "json"}``: lo
    costruiamo dalla risposta Flask (``status_code`` + ``get_json()``).
    """
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": resp.get_json(),
    }


def _valid_payload(**overrides) -> dict:
    """Body ``UserCreate`` valido (solo i campi ammessi dal contratto)."""
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada.lovelace@example.com",
        "company": "Analytical Engines",
        "role": "attendee",
    }
    payload.update(overrides)
    return payload


def _create(client, **overrides):
    """Crea un utente via POST e restituisce la risposta Flask."""
    return client.post("/api/v1/users", json=_valid_payload(**overrides))


# --------------------------------------------------------------------------- #
# GET /health — REQ-USR-02
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-02")
def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "service": "user-service"}

    assert_matches_contract("user", "GET", "/health", _contract_response(resp))


# --------------------------------------------------------------------------- #
# POST /api/v1/users — REQ-USR-03, REQ-USR-13
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-03")
def test_create_user_201(client):
    resp = _create(client)

    assert resp.status_code == 201
    assert resp.headers.get("Location")  # header Location presente
    body = resp.get_json()
    assert body["id"]
    assert resp.headers["Location"] == f"/api/v1/users/{body['id']}"
    assert body["email"] == "ada.lovelace@example.com"

    assert_matches_contract("user", "POST", "/api/v1/users", _contract_response(resp))


@pytest.mark.req("REQ-USR-13")
def test_create_missing_field_422(client):
    payload = _valid_payload()
    del payload["first_name"]

    resp = client.post("/api/v1/users", json=payload)

    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"

    assert_matches_contract("user", "POST", "/api/v1/users", _contract_response(resp))


@pytest.mark.req("REQ-USR-09")
def test_create_duplicate_email_409(client):
    first = _create(client, email="dup@example.com")
    assert first.status_code == 201

    # Stessa email ma con case diverso → deve essere rifiutata (case-insensitive).
    resp = _create(client, email="DUP@Example.COM")

    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    assert_matches_contract("user", "POST", "/api/v1/users", _contract_response(resp))


@pytest.mark.req("REQ-USR-13")
def test_create_malformed_json_400(client):
    resp = client.post(
        "/api/v1/users",
        data="{bad",
        content_type="application/json",
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"

    assert_matches_contract("user", "POST", "/api/v1/users", _contract_response(resp))


# --------------------------------------------------------------------------- #
# GET /api/v1/users — REQ-USR-04, REQ-USR-11
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-04")
def test_list_users_200(client):
    _create(client, email="a@example.com")
    _create(client, email="b@example.com")
    _create(client, email="c@example.com")

    resp = client.get("/api/v1/users")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 3

    assert_matches_contract("user", "GET", "/api/v1/users", _contract_response(resp))


@pytest.mark.req("REQ-USR-11")
def test_list_filter_role_200(client):
    _create(client, email="att@example.com", role="attendee")
    _create(client, email="spk@example.com", role="speaker")

    resp = client.get("/api/v1/users?role=speaker")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert all(u["role"] == "speaker" for u in body["items"])

    assert_matches_contract("user", "GET", "/api/v1/users", _contract_response(resp))


@pytest.mark.req("REQ-USR-13")
def test_list_invalid_page_size_422(client):
    resp = client.get("/api/v1/users?page_size=500")

    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"

    assert_matches_contract("user", "GET", "/api/v1/users", _contract_response(resp))


# --------------------------------------------------------------------------- #
# GET /api/v1/users/<id> — REQ-USR-05
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-05")
def test_get_user_200(client):
    created = _create(client).get_json()
    user_id = created["id"]

    resp = client.get(f"/api/v1/users/{user_id}")

    assert resp.status_code == 200
    assert resp.get_json()["id"] == user_id

    assert_matches_contract(
        "user", "GET", f"/api/v1/users/{user_id}", _contract_response(resp)
    )


@pytest.mark.req("REQ-USR-05")
def test_get_user_404(client):
    resp = client.get("/api/v1/users/does-not-exist")

    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"

    assert_matches_contract(
        "user", "GET", "/api/v1/users/does-not-exist", _contract_response(resp)
    )


# --------------------------------------------------------------------------- #
# PUT /api/v1/users/<id> — REQ-USR-06
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-06")
def test_put_user_200(client):
    created = _create(client).get_json()
    user_id = created["id"]

    resp = client.put(
        f"/api/v1/users/{user_id}",
        json=_valid_payload(first_name="Grace", last_name="Hopper", role="speaker"),
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == user_id
    assert body["first_name"] == "Grace"
    assert body["role"] == "speaker"

    assert_matches_contract(
        "user", "PUT", f"/api/v1/users/{user_id}", _contract_response(resp)
    )


@pytest.mark.req("REQ-USR-06")
def test_put_user_404(client):
    resp = client.put("/api/v1/users/does-not-exist", json=_valid_payload())

    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"

    assert_matches_contract(
        "user", "PUT", "/api/v1/users/does-not-exist", _contract_response(resp)
    )


# --------------------------------------------------------------------------- #
# PATCH /api/v1/users/<id> — REQ-USR-07
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-07")
def test_patch_user_200(client):
    created = _create(client).get_json()
    user_id = created["id"]

    resp = client.patch(f"/api/v1/users/{user_id}", json={"first_name": "Edith"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == user_id
    assert body["first_name"] == "Edith"
    # Gli altri campi restano invariati.
    assert body["last_name"] == created["last_name"]

    assert_matches_contract(
        "user", "PATCH", f"/api/v1/users/{user_id}", _contract_response(resp)
    )


@pytest.mark.req("REQ-USR-07")
def test_patch_user_404(client):
    resp = client.patch("/api/v1/users/does-not-exist", json={"first_name": "Edith"})

    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"

    assert_matches_contract(
        "user", "PATCH", "/api/v1/users/does-not-exist", _contract_response(resp)
    )


# --------------------------------------------------------------------------- #
# DELETE /api/v1/users/<id> — REQ-USR-08
# --------------------------------------------------------------------------- #
@pytest.mark.req("REQ-USR-08")
def test_delete_user_204(client):
    created = _create(client).get_json()
    user_id = created["id"]

    resp = client.delete(f"/api/v1/users/{user_id}")

    assert resp.status_code == 204
    assert resp.data == b""  # nessun body

    # Il validator accetta l'assenza di body per lo status 204.
    assert_matches_contract(
        "user", "DELETE", f"/api/v1/users/{user_id}", _contract_response(resp)
    )

    # Dopo il DELETE l'utente non è più raggiungibile.
    follow_up = client.get(f"/api/v1/users/{user_id}")
    assert follow_up.status_code == 404


@pytest.mark.req("REQ-USR-08")
def test_delete_user_404(client):
    resp = client.delete("/api/v1/users/does-not-exist")

    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"

    assert_matches_contract(
        "user", "DELETE", "/api/v1/users/does-not-exist", _contract_response(resp)
    )
