"""Service d'interaction avec Exchange/Outlook."""

import json
import os
import re
import datetime
from typing import Any, Dict, List, Optional

import pytz
from exchangelib import Configuration, Credentials, Account, DELEGATE

from src.utils.datetime_utils import to_py_datetime
from src.utils.retry_utils import retry_call

# L'autodiscover est lent et c'est le point de défaillance le plus fréquent des
# runs (« All steps in the autodiscover protocol failed »). On mémorise l'endpoint
# EWS résolu pour s'en passer aux runs suivants.
DEFAULT_ENDPOINT_CACHE = '.exchange_endpoint.json'


def clean_subject(subject: Optional[str]) -> str:
    """Nettoie le titre des événements Outlook."""
    if not subject:
        return 'Sans titre'

    # Supprime le tag [MAIL EXTERNE]
    subject = re.sub(r'\[MAIL EXTERNE\]', '', subject)

    # Normalise les espaces
    return re.sub(r'\s+', ' ', subject).strip()


def sync_key(item: Any) -> str:
    """Construit une identité stable pour un élément de calendrier Exchange.

    `item.id` (ItemId EWS) n'est pas une identité : il change quand l'élément est
    recréé côté serveur (typiquement les absences poussées par l'outil RH), ce qui
    provoque une boucle suppression/recréation à chaque synchronisation.

    `item.uid` (iCalUID) est stable, mais partagé par toutes les occurrences d'une
    série récurrente. On le combine donc avec `recurrence_id` (calendar:RecurrenceId),
    qui identifie l'occurrence et reste stable même si elle est déplacée.
    """
    uid = getattr(item, 'uid', None)

    if not uid:
        return str(item.id)

    recurrence_id = getattr(item, 'recurrence_id', None)

    if recurrence_id is None:
        return str(uid)

    return f"{uid}|{recurrence_id.isoformat()}"


class ExchangeCalendarService:
    """Gère les interactions avec Exchange/Outlook."""

    def __init__(self, username: str, email: str, password: str,
                 endpoint_cache_path: str = DEFAULT_ENDPOINT_CACHE):
        """Initialise le service Exchange."""
        self.username = username
        self.email = email
        self.password = password
        self.endpoint_cache_path = endpoint_cache_path
        self.account = None

    def connect(self) -> bool:
        """Établit la connexion avec le serveur Exchange."""
        credentials = Credentials(username=self.username, password=self.password)
        cached = self._load_cached_endpoint()

        if cached:
            try:
                self.account = self._connect_to_endpoint(credentials, cached)
                print(f"✅ Connecté à Exchange : {self.account.primary_smtp_address} "
                      f"(endpoint en cache)")
                return True
            except Exception as e:
                # Un endpoint mémorisé peut devenir obsolète (migration de
                # serveur) : on l'oublie et on repasse par l'autodiscover.
                print(f"⚠️ Endpoint Exchange en cache inutilisable "
                      f"({type(e).__name__}), retour à l'autodiscover")
                self._forget_cached_endpoint()

        try:
            self.account = retry_call(
                lambda: self._connect_with_autodiscover(credentials),
                label="connexion Exchange (autodiscover)")
            print(f"✅ Connecté à Exchange : {self.account.primary_smtp_address}")
            self._save_endpoint()
            return True
        except Exception as e:
            print(f"❌ Erreur de connexion Exchange : {e}")
            return False

    def _connect_with_autodiscover(self, credentials: Credentials) -> Account:
        return Account(
            primary_smtp_address=self.email,
            credentials=credentials,
            autodiscover=True,
            access_type=DELEGATE
        )

    def _connect_to_endpoint(self, credentials: Credentials, cached: Dict) -> Account:
        config = Configuration(
            credentials=credentials,
            service_endpoint=cached['service_endpoint'],
            auth_type=cached.get('auth_type')
        )
        account = Account(
            primary_smtp_address=self.email,
            config=config,
            autodiscover=False,
            access_type=DELEGATE
        )
        # Force un aller-retour maintenant : sans cela un endpoint obsolète ne
        # se manifesterait qu'au premier appel réel, hors du repli.
        _ = account.version
        return account

    def _load_cached_endpoint(self) -> Optional[Dict]:
        try:
            with open(self.endpoint_cache_path) as fh:
                cached = json.load(fh)
        except (OSError, ValueError):
            return None

        return cached if cached.get('service_endpoint') else None

    def _save_endpoint(self) -> None:
        try:
            protocol = self.account.protocol
            payload = {'service_endpoint': protocol.service_endpoint,
                       'auth_type': protocol.auth_type}

            with open(self.endpoint_cache_path, 'w') as fh:
                json.dump(payload, fh)
        except Exception as e:
            # Le cache est une optimisation : son échec ne doit rien casser.
            print(f"⚠️ Impossible de mémoriser l'endpoint Exchange : {e}")

    def _forget_cached_endpoint(self) -> None:
        try:
            os.remove(self.endpoint_cache_path)
        except OSError:
            pass

    def get_events(self, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict]:
        """Récupère les événements du calendrier Exchange."""
        if not self.account:
            raise RuntimeError("Non connecté à Exchange. Appelez connect() d'abord.")

        events = []

        # Lecture idempotente : on peut la rejouer sans risque après un timeout.
        items = retry_call(
            lambda: self.account.calendar.view(start=start_date, end=end_date).order_by('start'),
            label="lecture du calendrier Exchange")

        for item in items:
            all_day = isinstance(item.start, datetime.date) and not isinstance(item.start, datetime.datetime)

            start_dt = to_py_datetime(item.start)
            end_dt = to_py_datetime(item.end)

            if not start_dt or not end_dt:
                continue

            if all_day:
                # exchangelib traite les deux bornes comme INCLUSIVES pour les journées
                # entières, alors que Google Calendar attend un `end` EXCLUSIF.
                # On normalise ici sur la convention Google, valable pour tout le reste
                # de la chaîne de synchronisation.
                end_dt += datetime.timedelta(days=1)

            event = {
                'uid': sync_key(item),
                'item_id': str(item.id),
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
