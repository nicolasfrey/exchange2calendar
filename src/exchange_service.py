"""Service d'interaction avec Exchange/Outlook."""

import re
import datetime
from typing import Dict, List, Optional

import pytz
from exchangelib import Credentials, Account, DELEGATE

from src.utils.datetime_utils import to_py_datetime


def clean_subject(subject: Optional[str]) -> str:
    """Nettoie le titre des événements Outlook."""
    if not subject:
        return 'Sans titre'

    # Supprime le tag [MAIL EXTERNE]
    subject = re.sub(r'\[MAIL EXTERNE\]', '', subject)

    # Normalise les espaces
    return re.sub(r'\s+', ' ', subject).strip()


class ExchangeCalendarService:
    """Gère les interactions avec Exchange/Outlook."""

    def __init__(self, username: str, email: str, password: str):
        """Initialise le service Exchange."""
        self.username = username
        self.email = email
        self.password = password
        self.account = None

    def connect(self) -> bool:
        """Établit la connexion avec le serveur Exchange."""
        try:
            credentials = Credentials(username=self.username, password=self.password)
            self.account = Account(
                primary_smtp_address=self.email,
                credentials=credentials,
                autodiscover=True,
                access_type=DELEGATE
            )
            print(f"✅ Connecté à Exchange : {self.account.primary_smtp_address}")
            return True
        except Exception as e:
            print(f"❌ Erreur de connexion Exchange : {e}")
            return False

    def get_events(self, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict]:
        """Récupère les événements du calendrier Exchange."""
        if not self.account:
            raise RuntimeError("Non connecté à Exchange. Appelez connect() d'abord.")

        events = []

        for item in self.account.calendar.view(start=start_date, end=end_date).order_by('start'):
            start_dt = to_py_datetime(item.start)
            end_dt = to_py_datetime(item.end)

            if not start_dt or not end_dt:
                continue

            all_day = isinstance(item.start, datetime.date) and not isinstance(item.start, datetime.datetime)

            event = {
                'uid': str(item.id),
                'subject': clean_subject(item.subject),
                'location': item.location or '',
                'start': start_dt,
                'end': end_dt,
                'all_day': all_day,
                'body': str(item.text_body) if item.text_body else '',
                'organizer': str(item.organizer.email_address) if item.organizer else '',
            }

            events.append(event)

        return events
