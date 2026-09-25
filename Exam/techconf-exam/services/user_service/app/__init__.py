"""Factory dell'applicazione Flask del user-service."""

from flask import Flask


def create_app(repo=None):
    """Crea e configura l'app Flask.

    :param repo: repository opzionale iniettato per i test (dependency
        injection). Se ``None``, i task successivi useranno
        ``get_repository()`` per selezionare il backend da ``STORAGE_BACKEND``.
    """
    app = Flask(__name__)

    # Import locale del blueprint: evita import circolari e permette che la
    # factory funzioni anche prima che service.py/repository.py esistano.
    from .routes import bp

    if repo is not None:
        bp.repo = repo

    app.register_blueprint(bp)
    return app
