"""Router Flask del user-service.

Livello HTTP del servizio: fa il parsing del body JSON, valida i tipi/parametri
HTTP di base, delega la logica di business al :class:`app.service.UserService`
e costruisce la risposta (status code, header ``Location``). NON contiene
alcuna regola di business ``REQ-USR-B*`` (quelle vivono nel service layer).

Le eccezioni custom sollevate dal service layer sono mappate ai rispettivi
codici HTTP tramite error handler registrati a livello di applicazione:

    ValidationError          -> 422 VALIDATION_ERROR
    EmailAlreadyExistsError  -> 409 EMAIL_ALREADY_EXISTS
    NotFoundError            -> 404 NOT_FOUND
    BadRequest (werkzeug)    -> 400 MALFORMED_JSON
    MethodNotAllowed         -> 405 METHOD_NOT_ALLOWED

Formato errore standard (REQ-USR-13.4):

    {"error": {"code": "UPPER_SNAKE", "message": "...", "details": {}}}

Endpoint registrati:

    GET    /health
    POST   /api/v1/users
    GET    /api/v1/users
    GET    /api/v1/users/<id>
    PUT    /api/v1/users/<id>
    PATCH  /api/v1/users/<id>
    DELETE /api/v1/users/<id>

Requirements: REQ-USR-02, REQ-USR-03, REQ-USR-04, REQ-USR-05, REQ-USR-06,
REQ-USR-07, REQ-USR-08, REQ-USR-11, REQ-USR-13.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, MethodNotAllowed

from .service import UserService
from .models import ROLES
from .exceptions import (
    ValidationError,
    EmailAlreadyExistsError,
    NotFoundError,
)

bp = Blueprint("api", __name__)

# Il repository viene iniettato dalla factory ``create_app`` (dependency
# injection). Gli endpoint vi accedono tramite ``bp.repo`` costruendo un
# ``UserService`` on-demand.
bp.repo = None


# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #


def _service() -> UserService:
    """Costruisce un :class:`UserService` sul repository iniettato dalla factory."""
    return UserService(bp.repo)


def _error(code: str, message: str, status: int, details: dict | None = None):
    """Costruisce una risposta di errore nel formato standard del contratto."""
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                }
            }
        ),
        status,
    )


def _parse_body() -> dict:
    """Fa il parsing del body JSON per POST/PUT/PATCH.

    Usa ``get_json(silent=True)`` (senza ``force``) per non mascherare i body
    malformati. Se il parsing fallisce ma ci sono byte nel corpo della
    richiesta, il body è malformato → solleva :class:`BadRequest` (400
    MALFORMED_JSON tramite error handler). Se il body è vuoto restituisce un
    dict vuoto, lasciando che sia il service layer a segnalare i campi
    obbligatori mancanti (422).
    """
    data = request.get_json(silent=True)
    if data is None:
        if request.data and request.data.strip():
            # Byte presenti ma non-parsabili come JSON → malformato.
            raise BadRequest("Request body is not valid JSON")
        # Body vuoto: il service layer segnalera i campi mancanti.
        return {}
    return data


# --------------------------------------------------------------------------- #
# Health — REQ-USR-02
# --------------------------------------------------------------------------- #


@bp.route("/health", methods=["GET"])
def health():
    """Health check — REQ-USR-02.

    Restituisce lo schema ``Health`` del contratto OpenAPI.
    """
    return jsonify({"status": "ok", "service": "user-service"}), 200


# --------------------------------------------------------------------------- #
# CREATE — POST /api/v1/users — REQ-USR-03
# --------------------------------------------------------------------------- #


@bp.route("/api/v1/users", methods=["POST"])
def create_user():
    """Crea un nuovo utente e risponde 201 con header ``Location``."""
    data = _parse_body()
    user = _service().create_user(data)
    response = jsonify(user)
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/users/{user['id']}"
    return response


# --------------------------------------------------------------------------- #
# LIST — GET /api/v1/users — REQ-USR-04, REQ-USR-11
# --------------------------------------------------------------------------- #


def _parse_int_param(name: str, raw: str, *, minimum: int, maximum: int | None = None) -> int:
    """Converte un query param in intero validandone i limiti.

    Solleva :class:`ValidationError` (422) se non intero o fuori intervallo.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"Query parameter '{name}' must be an integer", name)
    if value < minimum:
        raise ValidationError(
            f"Query parameter '{name}' must be >= {minimum}", name
        )
    if maximum is not None and value > maximum:
        raise ValidationError(
            f"Query parameter '{name}' must be <= {maximum}", name
        )
    return value


@bp.route("/api/v1/users", methods=["GET"])
def list_users():
    """Restituisce la lista paginata degli utenti applicando i filtri."""
    args = request.args

    page = _parse_int_param("page", args.get("page", "1"), minimum=1)
    page_size = _parse_int_param(
        "page_size", args.get("page_size", "20"), minimum=1, maximum=100
    )

    filters: dict = {}

    role = args.get("role")
    if role is not None:
        if role not in ROLES:
            raise ValidationError(
                f"Query parameter 'role' must be one of {', '.join(ROLES)}", "role"
            )
        filters["role"] = role

    email = args.get("email")
    if email is not None:
        filters["email"] = email

    data = _service().list_users(filters, page, page_size)
    return jsonify(data), 200


# --------------------------------------------------------------------------- #
# GET — GET /api/v1/users/<id> — REQ-USR-05
# --------------------------------------------------------------------------- #


@bp.route("/api/v1/users/<id>", methods=["GET"])
def get_user(id: str):
    """Restituisce il singolo utente o 404 (NotFoundError → handler)."""
    return jsonify(_service().get_user(id)), 200


# --------------------------------------------------------------------------- #
# PUT (replace) — PUT /api/v1/users/<id> — REQ-USR-06
# --------------------------------------------------------------------------- #


@bp.route("/api/v1/users/<id>", methods=["PUT"])
def replace_user(id: str):
    """Sostituisce integralmente un utente esistente e risponde 200."""
    data = _parse_body()
    return jsonify(_service().replace_user(id, data)), 200


# --------------------------------------------------------------------------- #
# PATCH (partial update) — PATCH /api/v1/users/<id> — REQ-USR-07
# --------------------------------------------------------------------------- #


@bp.route("/api/v1/users/<id>", methods=["PATCH"])
def update_user(id: str):
    """Aggiorna parzialmente un utente esistente e risponde 200."""
    data = _parse_body()
    return jsonify(_service().update_user(id, data)), 200


# --------------------------------------------------------------------------- #
# DELETE — DELETE /api/v1/users/<id> — REQ-USR-08
# --------------------------------------------------------------------------- #


@bp.route("/api/v1/users/<id>", methods=["DELETE"])
def delete_user(id: str):
    """Elimina un utente esistente e risponde 204 senza body."""
    _service().delete_user(id)
    return "", 204


# --------------------------------------------------------------------------- #
# Error handlers (app-level) — REQ-USR-13
# --------------------------------------------------------------------------- #


@bp.app_errorhandler(ValidationError)
def handle_validation(e: ValidationError):
    details = {"field": e.field} if getattr(e, "field", None) else {}
    return _error("VALIDATION_ERROR", str(e), 422, details)


@bp.app_errorhandler(EmailAlreadyExistsError)
def handle_conflict(e: EmailAlreadyExistsError):
    return _error("EMAIL_ALREADY_EXISTS", str(e), 409)


@bp.app_errorhandler(NotFoundError)
def handle_not_found(e: NotFoundError):
    return _error("NOT_FOUND", str(e), 404)


@bp.app_errorhandler(BadRequest)
def handle_bad_request(e: BadRequest):
    return _error("MALFORMED_JSON", "Request body is not valid JSON", 400)


@bp.app_errorhandler(MethodNotAllowed)
def handle_method_not_allowed(e: MethodNotAllowed):
    return _error("METHOD_NOT_ALLOWED", "Method not allowed for this resource", 405)
