"""Entry point alternativo: ``python run.py``.

Equivalente a ``python -m app``. La suite di collaudo usa ``python -m app``
(vedi services.yaml), ma questo file è richiesto da REQ-USR-01.4.
"""

from app import create_app
from app.config import PORT

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=PORT)
