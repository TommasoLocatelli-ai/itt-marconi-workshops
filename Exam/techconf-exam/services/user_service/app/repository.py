"""Repository layer del user-service.

Questo modulo è l'unico che conosce il dettaglio dello *storage*. Espone
un'interfaccia comune :class:`UserRepository` e tre implementazioni
intercambiabili:

* :class:`MemoryRepository` — dizionario in memoria, volatile (default).
* :class:`JsonRepository` — file ``{DATA_DIR}/users.json`` con scrittura atomica.
* :class:`SqliteRepository` — file ``{DATA_DIR}/users.db`` via ``sqlite3`` stdlib.

La factory :func:`get_repository` seleziona il backend leggendo
``config.STORAGE_BACKEND`` (mai ``os.environ`` direttamente), con fallback
sicuro a :class:`MemoryRepository` per qualsiasi valore non riconosciuto
(REQ-USR-01.7).

Tutti i metodi lavorano su ``user dict`` (la rappresentazione serializzata
prodotta da :meth:`app.models.User.to_dict`). Le regole:

* ``email_exists`` confronta le email in modo **case-insensitive** ed è in grado
  di escludere un utente specifico (``exclude_id``) per gli aggiornamenti.
* ``find_all`` applica i filtri ``role`` (match esatto) ed ``email`` (match
  case-insensitive) in **AND** logico e ordina per ``created_at`` crescente per
  garantire un output deterministico.

Requirements: REQ-USR-01, REQ-USR-12.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from typing import Optional

from . import config


# Colonne della risorsa User nell'ordine usato dallo schema SQLite.
_COLUMNS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "company",
    "role",
    "created_at",
    "updated_at",
)


def _matches_filters(user: dict, filters: Optional[dict]) -> bool:
    """Verifica se ``user`` soddisfa TUTTI i filtri forniti (AND logico).

    Filtri supportati:

    * ``role`` — match esatto sul campo ``role``.
    * ``email`` — match case-insensitive sul campo ``email``.

    Valori di filtro ``None`` o vuoti vengono ignorati.
    """
    if not filters:
        return True

    role = filters.get("role")
    if role:
        if user.get("role") != role:
            return False

    email = filters.get("email")
    if email:
        user_email = (user.get("email") or "").lower()
        if user_email != email.lower():
            return False

    return True


def _sort_by_created_at(users: list[dict]) -> list[dict]:
    """Ordina gli utenti per ``created_at`` crescente (output deterministico)."""
    return sorted(users, key=lambda u: (u.get("created_at") or "", u.get("id") or ""))


class UserRepository:
    """Interfaccia comune ai backend di persistenza degli utenti.

    Le sottoclassi devono implementare tutti e cinque i metodi. La classe base
    solleva :class:`NotImplementedError` per rendere esplicito il contratto.
    """

    def find_by_id(self, id: str) -> Optional[dict]:
        """Restituisce l'utente con quell'``id`` oppure ``None`` se assente."""
        raise NotImplementedError

    def find_all(self, filters: dict) -> list[dict]:
        """Restituisce gli utenti che soddisfano i filtri, ordinati per data."""
        raise NotImplementedError

    def save(self, user: dict) -> dict:
        """Inserisce (se ``id`` nuovo) o sostituisce (se esistente) e restituisce."""
        raise NotImplementedError

    def delete(self, id: str) -> bool:
        """Elimina l'utente; ``True`` se esisteva, ``False`` altrimenti."""
        raise NotImplementedError

    def email_exists(self, email: str, exclude_id: Optional[str] = None) -> bool:
        """Indica se esiste (case-insensitive) un altro utente con quell'email."""
        raise NotImplementedError


class MemoryRepository(UserRepository):
    """Backend in-memory basato su ``dict`` ``{id: user_dict}``.

    Lo stato vive nel processo e viene perso al riavvio; non è thread-safe,
    condizione accettabile per test e sviluppo.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def find_by_id(self, id: str) -> Optional[dict]:
        user = self._store.get(id)
        return dict(user) if user is not None else None

    def find_all(self, filters: dict) -> list[dict]:
        result = [
            dict(u) for u in self._store.values() if _matches_filters(u, filters)
        ]
        return _sort_by_created_at(result)

    def save(self, user: dict) -> dict:
        self._store[user["id"]] = dict(user)
        return dict(user)

    def delete(self, id: str) -> bool:
        return self._store.pop(id, None) is not None

    def email_exists(self, email: str, exclude_id: Optional[str] = None) -> bool:
        target = email.lower()
        for u in self._store.values():
            if u["id"] == exclude_id:
                continue
            if (u.get("email") or "").lower() == target:
                return True
        return False


class JsonRepository(UserRepository):
    """Backend su file JSON ``{DATA_DIR}/users.json``.

    Formato del file: ``{"users": [ {user_dict}, ... ]}``. Ogni operazione di
    scrittura usa una strategia *atomic read-modify-write*: legge lo stato
    corrente, lo modifica in memoria e riscrive su file temporaneo prima di
    rinominarlo (``os.replace``) sul file definitivo, evitando file corrotti in
    caso di crash a metà scrittura.

    ``data_dir`` viene letto da :mod:`app.config` al momento dell'istanziazione
    (default ``config.DATA_DIR``), così i test che usano ``monkeypatch`` +
    ``tmp_path`` funzionano correttamente.
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or config.DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "users.json")

    def _read_all(self) -> list[dict]:
        """Legge la lista utenti dal file (lista vuota se il file è assente)."""
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                return []
        users = data.get("users", []) if isinstance(data, dict) else []
        return [dict(u) for u in users]

    def _write_all(self, users: list[dict]) -> None:
        """Riscrive atomicamente l'intera lista utenti sul file JSON."""
        os.makedirs(self.data_dir, exist_ok=True)
        payload = {"users": users}
        # Scrittura su file temporaneo nella stessa directory + rename atomico.
        fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def find_by_id(self, id: str) -> Optional[dict]:
        for u in self._read_all():
            if u.get("id") == id:
                return u
        return None

    def find_all(self, filters: dict) -> list[dict]:
        result = [u for u in self._read_all() if _matches_filters(u, filters)]
        return _sort_by_created_at(result)

    def save(self, user: dict) -> dict:
        users = self._read_all()
        for i, existing in enumerate(users):
            if existing.get("id") == user["id"]:
                users[i] = dict(user)
                break
        else:
            users.append(dict(user))
        self._write_all(users)
        return dict(user)

    def delete(self, id: str) -> bool:
        users = self._read_all()
        remaining = [u for u in users if u.get("id") != id]
        if len(remaining) == len(users):
            return False
        self._write_all(remaining)
        return True

    def email_exists(self, email: str, exclude_id: Optional[str] = None) -> bool:
        target = email.lower()
        for u in self._read_all():
            if u.get("id") == exclude_id:
                continue
            if (u.get("email") or "").lower() == target:
                return True
        return False


class SqliteRepository(UserRepository):
    """Backend su database SQLite ``{DATA_DIR}/users.db`` (solo stdlib).

    La connessione viene aperta e chiusa a ogni operazione (semplice e adeguato
    al carico previsto). ``row_factory`` è impostata su ``sqlite3.Row`` per
    convertire facilmente i record in ``dict``.

    Il vincolo ``UNIQUE`` sulla colonna ``email`` garantisce l'unicità a livello
    di storage; la logica applicativa (``email_exists``) la verifica comunque
    esplicitamente prima di raggiungere il DB.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id          TEXT PRIMARY KEY,
        first_name  TEXT NOT NULL,
        last_name   TEXT NOT NULL,
        email       TEXT NOT NULL UNIQUE,
        company     TEXT,
        role        TEXT NOT NULL DEFAULT 'attendee',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or config.DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "users.db")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(self._SCHEMA)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        """Converte una ``Row`` in dict con ``company`` sempre presente."""
        return {
            "id": row["id"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "email": row["email"],
            "company": row["company"],  # può essere None
            "role": row["role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def find_by_id(self, id: str) -> Optional[dict]:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT * FROM users WHERE id = ?", (id,))
            row = cur.fetchone()
            return self._row_to_dict(row) if row is not None else None
        finally:
            conn.close()

    def find_all(self, filters: dict) -> list[dict]:
        clauses = []
        params: list = []
        if filters:
            role = filters.get("role")
            if role:
                clauses.append("role = ?")
                params.append(role)
            email = filters.get("email")
            if email:
                clauses.append("LOWER(email) = LOWER(?)")
                params.append(email)

        query = "SELECT * FROM users"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC, id ASC"

        conn = self._connect()
        try:
            cur = conn.execute(query, params)
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def save(self, user: dict) -> dict:
        values = tuple(user.get(col) for col in _COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns = ", ".join(_COLUMNS)
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO users ({columns}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
        finally:
            conn.close()
        return dict(user)

    def delete(self, id: str) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def email_exists(self, email: str, exclude_id: Optional[str] = None) -> bool:
        conn = self._connect()
        try:
            if exclude_id is not None:
                cur = conn.execute(
                    "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?) "
                    "AND id != ? LIMIT 1",
                    (email, exclude_id),
                )
            else:
                cur = conn.execute(
                    "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?) LIMIT 1",
                    (email,),
                )
            return cur.fetchone() is not None
        finally:
            conn.close()


def get_repository() -> UserRepository:
    """Factory che seleziona il backend in base a ``config.STORAGE_BACKEND``.

    * ``"json"``   → :class:`JsonRepository`
    * ``"sqlite"`` → :class:`SqliteRepository`
    * qualunque altro valore (incluso ``"memory"``) → :class:`MemoryRepository`
      (fallback sicuro, REQ-USR-01.7).

    Il valore viene letto da :mod:`app.config` (mai da ``os.environ``
    direttamente) e normalizzato a minuscolo.
    """
    backend = (config.STORAGE_BACKEND or "memory").lower()
    if backend == "json":
        return JsonRepository()
    if backend == "sqlite":
        return SqliteRepository()
    return MemoryRepository()
