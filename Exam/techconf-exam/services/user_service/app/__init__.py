"""Factory dell'applicazione Flask del user-service."""

from flask import Flask


def create_app(repo=None):
    """Crea e configura l'app Flask.

    :param repo: repository opzionale iniettato per i test (dependency
        injection). Se ``None``, i task successivi useranno
        ``get_repository()`` per selezionare il backend da ``STORAGE_BACKEND``.
    """
    app = Flask(__name__)

    # Se nessun repository e iniettato esplicitamente (tipico dei test), la
    # factory seleziona il backend configurato tramite get_repository().
    if repo is None:
        from .repository import get_repository
        repo = get_repository()

    # Import locale del blueprint: evita import circolari.
    from .routes import bp

    # Dependency injection: il router accede al repository via bp.repo e vi
    # costruisce sopra un UserService. bp.repo e un attributo condiviso a
    # livello di modulo; viene reimpostato a ogni create_app (ok per i test).
    bp.repo = repo

    app.register_blueprint(bp)
    return app
