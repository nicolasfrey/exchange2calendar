"""Réessai des opérations réseau transitoires."""

import logging
import time
from typing import Any, Callable, Iterable, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# Erreurs observées dans sync.log au réveil de la machine : résolution DNS,
# autodiscover Exchange, lecture qui expire, interruption TLS.
TRANSIENT_ERRORS: Tuple[Type[BaseException], ...] = (
    ConnectionError, TimeoutError, OSError,
)

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 5.0


def retry_call(operation: Callable[[], Any], *,
               attempts: int = DEFAULT_ATTEMPTS,
               base_delay: float = DEFAULT_BASE_DELAY,
               retry_on: Iterable[Type[BaseException]] = TRANSIENT_ERRORS,
               label: str = "opération",
               on_retry: Optional[Callable[[int, float, BaseException], None]] = None,
               sleep: Optional[Callable[[float], None]] = None) -> Any:
    """Exécute `operation` en réessayant les erreurs transitoires.

    Le délai double à chaque tentative (`base_delay`, ×2, ×4...). Aucune attente
    après la dernière tentative : l'erreur est propagée telle quelle.

    N'utiliser que pour des opérations idempotentes : réessayer une écriture qui
    a peut-être abouti recréerait un doublon.
    """
    retry_on = tuple(retry_on)
    # Résolu à l'appel et non dans la signature : une valeur par défaut est
    # évaluée une seule fois à l'import, ce qui rend `time.sleep` impatchable.
    pause = sleep or time.sleep
    last_error: Optional[BaseException] = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as error:
            last_error = error

            if attempt == attempts:
                break

            delay = base_delay * (2 ** (attempt - 1))

            if on_retry:
                on_retry(attempt, delay, error)
            else:
                logger.warning(f"⏳ {label} : échec ({type(error).__name__}), "
                      f"nouvelle tentative dans {delay:.0f}s "
                      f"({attempt}/{attempts - 1})")

            pause(delay)

    raise last_error
