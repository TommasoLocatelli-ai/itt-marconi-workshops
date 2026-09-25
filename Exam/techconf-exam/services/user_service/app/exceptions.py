"""Custom exceptions for the user-service.

Queste eccezioni sono sollevate dal service layer e mappate dal router
ai rispettivi codici HTTP:

    ValidationError         -> 422 VALIDATION_ERROR
    EmailAlreadyExistsError -> 409 EMAIL_ALREADY_EXISTS
    NotFoundError           -> 404 NOT_FOUND

Ogni eccezione chiama super().__init__(message) cosicche str(e) restituisca
il messaggio leggibile.

Requirements: REQ-USR-03, REQ-USR-05, REQ-USR-06, REQ-USR-07, REQ-USR-08
"""


class ValidationError(Exception):
    """Sollevata quando l'input non rispetta i vincoli di validazione.

    Firma (message, field=None): comoda da sollevare col solo messaggio.
    L'attributo opzionale ``field`` puo essere usato nel campo ``details``
    della risposta di errore.

    Mappata dal router a 422 VALIDATION_ERROR.
    """

    def __init__(self, message: str, field: "str | None" = None):
        self.field = field
        self.message = message
        super().__init__(message)


class EmailAlreadyExistsError(Exception):
    """Sollevata quando un'email e gia registrata (case-insensitive).

    Mappata dal router a 409 EMAIL_ALREADY_EXISTS.
    """

    def __init__(self, message: str = "Email already exists"):
        self.message = message
        super().__init__(message)


class NotFoundError(Exception):
    """Sollevata quando una risorsa richiesta non esiste.

    Mappata dal router a 404 NOT_FOUND.
    """

    def __init__(self, message: str = "Resource not found"):
        self.message = message
        super().__init__(message)
