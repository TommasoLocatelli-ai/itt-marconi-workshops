"""Configurazione del user-service.

Questo modulo è l'UNICO punto del servizio che legge da ``os.environ``.
Ogni altra parte del codice importa i valori da qui.
"""

import os

# Porta di ascolto Flask. In sviluppo il default è 5001, ma la suite di
# collaudo inietta sempre PORT (15001+), quindi non va mai hard-coded altrove.
PORT = int(os.environ.get("PORT", 5001))

# Backend di persistenza: memory | json | sqlite. Default: memory.
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "memory")

# Directory in cui vengono salvati i file json/sqlite.
DATA_DIR = os.environ.get("DATA_DIR", "./data")

# URL degli altri microservizi. Il user-service non chiama altri servizi, ma
# i default sono presenti per coerenza con la struttura comune del repository.
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:5001")
EVENT_SERVICE_URL = os.environ.get("EVENT_SERVICE_URL", "http://localhost:5002")
REGISTRATION_SERVICE_URL = os.environ.get(
    "REGISTRATION_SERVICE_URL", "http://localhost:5003"
)
