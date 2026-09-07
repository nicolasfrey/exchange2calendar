"""Service d'interaction avec l'API Google Calendar."""

import os
from typing import Any
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from src.utils.retry_utils import retry_call


def get_exchange_uid(event: dict) -> str:
    """Récupère l'UID Exchange stocké dans les propriétés privées Google.

    Renvoie une chaîne vide pour tout événement qui ne vient pas de la synchro :
    c'est ce qui protège les événements créés à la main dans le calendrier. Un
    repli sur `description` leur attribuerait un UID inconnu d'Exchange, et la
    passe de nettoyage les supprimerait.
    """
    try:
        properties = event.get('extendedProperties') or {}
        private = properties.get('private') or {}
        return private.get('exchange_uid') or ''
    except Exception:
        return ''


class GoogleCalendarService:
    """Gère les interactions avec l'API Google Calendar."""

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    @staticmethod
    def authenticate() -> Any:
        """Initialise et authentifie l'API Google Calendar."""
        creds = None

        # Charger les tokens depuis le fichier s'ils existent
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', GoogleCalendarService.SCOPES)

        # Renouveler les tokens expirés ou obtenir de nouveaux tokens
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', GoogleCalendarService.SCOPES)
                creds = flow.run_local_server(port=0)

            # Sauvegarder les credentials pour la prochaine exécution
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        # `build` résout le document de découverte : c'est un appel réseau, et
        # il échoue au réveil de la machine (« Unable to find the server at
        # www.googleapis.com »). Idempotent, donc réessayable.
        return retry_call(lambda: build('calendar', 'v3', credentials=creds),
                          label="connexion à l'API Google Calendar")
