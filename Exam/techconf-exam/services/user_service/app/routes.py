"""Router Flask del user-service.

Stub iniziale (Task 1): espone solo l'endpoint ``GET /health`` necessario a
far passare l'health check della suite di collaudo. Gli endpoint CRUD e gli
error handler verranno aggiunti nei task successivi (Task 7).
"""

from flask import Blueprint, jsonify

bp = Blueprint("api", __name__)

# Il repository viene iniettato dalla factory ``create_app`` (dependency
# injection). Negli endpoint futuri si accederà con ``bp.repo``.
bp.repo = None


@bp.route("/health", methods=["GET"])
def health():
    """Health check — REQ-USR-02.

    Restituisce lo schema ``Health`` del contratto OpenAPI.
    """
    return jsonify({"status": "ok", "service": "user-service"}), 200
