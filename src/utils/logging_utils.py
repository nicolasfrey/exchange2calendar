"""Configuration du journal de l'application."""

import logging
import sys
from typing import Optional, TextIO

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_HANDLER_NAME = "exchange-sync"

# Bibliothèques tierces bavardes en INFO : leur bruit noierait le journal de
# synchronisation (ex. « file_cache is only supported with oauth2client<4.0.0 »).
# Leurs avertissements et erreurs restent visibles.
NOISY_LIBRARIES = (
    "googleapiclient", "google", "google_auth_httplib2",
    "urllib3", "requests", "exchangelib",
)


def configure_logging(stream: Optional[TextIO] = None, level: int = logging.INFO) -> None:
    """Installe un handler unique qui horodate chaque ligne.

    Sans cela, le journal ne portait de date qu'au début et à la fin du run
    (posées par run_sync.sh) : impossible de situer l'étape d'un run interrompu.

    Idempotent : le handler est remplacé, jamais ajouté deux fois.
    """
    root = logging.getLogger()

    for existing in list(root.handlers):
        if getattr(existing, 'name', None) == _HANDLER_NAME:
            root.removeHandler(existing)

    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root.addHandler(handler)
    root.setLevel(level)

    for name in NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)
