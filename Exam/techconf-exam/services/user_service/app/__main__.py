"""Entry point per ``python -m app``.

La suite di collaudo avvia il servizio con ``command: python -m app`` e
inietta la variabile d'ambiente PORT. L'app ascolta su 0.0.0.0.
"""

from app import create_app
from app.config import PORT

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=PORT)
