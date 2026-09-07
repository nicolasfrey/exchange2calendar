"""Fonctions utilitaires pour l'intégration avec healthchecks.io."""

import logging
import os
from typing import Optional, Union

import requests
import urllib3

from src.utils.retry_utils import retry_call

logger = logging.getLogger(__name__)

PING_TIMEOUT = 10


def resolve_ssl_verify() -> Union[bool, str]:
    """Détermine la valeur `verify` à passer à requests.

    Le réseau de l'entreprise passe par un pare-feu Fortinet qui réémet les
    certificats TLS. Sa CA est présente dans le magasin système, mais `requests`
    utilise par défaut le bundle embarqué de certifi, qui ne la contient pas :
    d'où les SSLError. Renseigner `CA_BUNDLE` (ex.
    /etc/ssl/certs/ca-certificates.crt) permet de garder la vérification ACTIVE.

    `VERIFY_SSL=false` reste disponible comme échappatoire et prime sur tout.
    """
    if os.getenv("VERIFY_SSL", "true").lower() == "false":
        return False

    return os.getenv("CA_BUNDLE") or True


def send_healthcheck_ping(status: Optional[str] = None, message: Optional[str] = None) -> bool:
    """
    Envoie un ping à healthchecks.io.

    Args:
        status: État du ping ('start', 'success', 'fail', None pour un ping standard)
        message: Message à inclure avec le ping (uniquement pour les échecs)

    Returns:
        bool: True si le ping a été envoyé avec succès, False sinon
    """
    healthcheck_url = os.getenv("HEALTHCHECK_URL")

    if not healthcheck_url:
        logger.error("❌ HEALTHCHECK_URL n'est pas définie dans les variables d'environnement")
        return False

    verify = resolve_ssl_verify()

    if verify is False:
        logger.warning("⚠️ Vérification SSL désactivée pour les requêtes healthchecks.io")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Le statut n'est ajouté à l'URL que pour 'start' et 'fail' ; 'success'
    # utilise l'URL de base.
    url = f"{healthcheck_url}/{status}" if status in ('start', 'fail') else healthcheck_url

    def ping():
        if message and status in ("fail", "success"):
            return requests.post(url, data=message.encode('utf-8'),
                                 timeout=PING_TIMEOUT, verify=verify)
        return requests.get(url, timeout=PING_TIMEOUT, verify=verify)

    try:
        # Idempotent : un ping rejoué ne fait qu'écraser le même état.
        response = retry_call(ping, label=f"ping healthcheck ({status or 'standard'})")

        if response.status_code != 200:
            logger.error(f"❌ Erreur lors de l'envoi du ping healthcheck ({status}): "
                  f"Code HTTP {response.status_code}")
            logger.info(f"Réponse: {response.text}")
        else:
            logger.info(f"✅ Ping healthcheck envoyé avec succès ({status or 'standard'})")

        return response.status_code == 200
    except requests.RequestException as e:
        logger.error(f"❌ Exception lors de l'envoi du ping healthcheck ({status}): "
              f"{type(e).__name__}: {str(e)}")

        if isinstance(e, requests.ConnectionError):
            logger.info("  → Vérifiez votre connexion internet ou l'URL du healthcheck")
        elif isinstance(e, requests.Timeout):
            logger.info("  → Le délai d'attente a été dépassé lors de la connexion au serveur")

        return False
