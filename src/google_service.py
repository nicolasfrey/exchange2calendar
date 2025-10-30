"""Service d'interaction avec l'API Google Calendar."""

import os
from typing import Any
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


def get_exchange_uid(event: dict) -> str:
    """Récupère l'UID Exchange stocké dans les propriétés privées Google."""
    try:
        return event.get('extendedProperties', {}).get('private', {}).get('exchange_uid', '') or event.get('description', '')
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

        return build('calendar', 'v3', credentials=creds)
