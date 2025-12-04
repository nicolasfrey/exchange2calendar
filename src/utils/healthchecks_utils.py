"""Fonctions utilitaires pour l'intégration avec healthchecks.io."""

import os
import requests
from typing import Optional


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
        print("❌ HEALTHCHECK_URL n'est pas définie dans les variables d'environnement")
        return False

    # Vérifier si la vérification SSL doit être désactivée
    verify_ssl = os.getenv("VERIFY_SSL", "true").lower() != "false"

    if not verify_ssl:
        print("⚠️ Vérification SSL désactivée pour les requêtes healthchecks.io")
        # Supprimer les avertissements de sécurité si la vérification SSL est désactivée
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    # Construire l'URL complète avec le statut si fourni
    url = healthcheck_url
    # Ajouter le statut à l'URL uniquement pour 'start' et 'fail'
    if status and status in ['start', 'fail']:
        url = f"{healthcheck_url}/{status}"
    # Pour 'success', on utilise l'URL de base sans suffixe

    try:
        # Ajouter le message en cas d'échec ou de succès
        if message and (status == "fail" or status == "success"):
            response = requests.post(url, data=message.encode('utf-8'), timeout=10, verify=verify_ssl)
        else:
            print(f"url: {url}")
            response = requests.get(url, timeout=10, verify=verify_ssl)

        if response.status_code != 200:
            print(f"❌ Erreur lors de l'envoi du ping healthcheck ({status}): Code HTTP {response.status_code}")
            print(f"Réponse: {response.text}")
        else:
            print(f"✅ Ping healthcheck envoyé avec succès ({status or 'standard'})")

        return response.status_code == 200
    except requests.RequestException as e:
        # Afficher l'erreur pour faciliter le débogage
        print(f"❌ Exception lors de l'envoi du ping healthcheck ({status}): {type(e).__name__}: {str(e)}")

        # Si c'est une erreur de connexion, afficher plus de détails
        if isinstance(e, requests.ConnectionError):
            print("  → Vérifiez votre connexion internet ou l'URL du healthcheck")
        elif isinstance(e, requests.Timeout):
            print("  → Le délai d'attente a été dépassé lors de la connexion au serveur")

        return False