"""Gestion de la synchronisation entre Exchange et Google Calendar."""

import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pytz

from src.utils.datetime_utils import (
    to_utc_datetime, normalize_str, datetimes_equal, parse_google_start
)
from src.google_service import get_exchange_uid
from src.utils.retry_utils import retry_call

# Fenêtre de rattrapage en amont : on interroge Google un peu plus tôt qu'Exchange
# afin de voir (et réparer/dédoublonner) les événements laissés par les runs passés.
DEFAULT_LOOKBACK_DAYS = 7

# Taille de page maximale acceptée par l'API Google Calendar (défaut implicite : 250).
GOOGLE_PAGE_SIZE = 2500

# Longueur maximale d'une description Google Calendar.
GOOGLE_DESCRIPTION_MAX_CHARS = 8192


def truncate_description(body: str) -> str:
    """Tronque un corps d'événement à la limite acceptée par Google Calendar."""
    return (body or '')[:GOOGLE_DESCRIPTION_MAX_CHARS]


class CalendarSynchronizer:
    """Gère la synchronisation entre Exchange et Google Calendar."""

    def __init__(self, exchange_service: Any, google_service: Any, calendar_id: str,
                 timezone: str, clock: Optional[Callable[[], datetime.datetime]] = None,
                 lookback_days: int = DEFAULT_LOOKBACK_DAYS):
        """Initialise le synchronisateur.

        `clock` permet d'injecter l'instant courant (utile pour les tests).
        """
        self.exchange_service = exchange_service
        self.google_service = google_service
        self.calendar_id = calendar_id
        self.timezone = timezone
        self.clock = clock or (lambda: datetime.datetime.now(pytz.UTC))
        self.lookback_days = lookback_days

    def synchronize(self, days_ahead: int, dry_run: bool = False) -> Tuple[int, int, int]:
        """Synchronise les événements entre Exchange et Google Calendar."""
        now = self.clock()

        # La fenêtre démarre à minuit (heure locale) et non à `now` : sinon un
        # événement du jour déjà commencé sort de la vue Exchange alors que sa
        # copie Google reste visible, ce qui rend les deux côtés incomparables.
        window_start = self._start_of_local_day(now)
        window_end = now + datetime.timedelta(days=days_ahead)

        print(f"📥 Lecture des événements Outlook du {window_start.date()} au {window_end.date()}...")

        outlook_events = self.exchange_service.get_events(window_start, window_end)
        self._display_events_summary(outlook_events)

        if dry_run:
            print("\n🔎 Mode simulation (--dry-run). Aucun changement ne sera appliqué.")

        print("\n🔗 Connexion à Google Calendar...")

        google_events = self._list_google_events(
            window_start - datetime.timedelta(days=self.lookback_days), window_end)

        google_index, duplicates = self._index_google_events(google_events)
        exchange_uids = {ev['uid'] for ev in outlook_events}

        created, updated, deleted = self._process_events(
            outlook_events, google_index, duplicates, exchange_uids, window_start, dry_run)

        print(f"\n✅ Synchronisation terminée : {created} créés, {updated} mis à jour, {deleted} supprimés.")
        return created, updated, deleted

    def _start_of_local_day(self, moment: datetime.datetime) -> datetime.datetime:
        """Minuit, dans le fuseau du calendrier, du jour de `moment`."""
        tz = pytz.timezone(self.timezone)
        local_day = moment.astimezone(tz).date()
        midnight = tz.localize(datetime.datetime.combine(local_day, datetime.time.min))
        return midnight.astimezone(pytz.UTC)

    def _list_google_events(self, time_min: datetime.datetime,
                            time_max: datetime.datetime) -> List[Dict]:
        """Liste TOUS les événements Google de la fenêtre, en suivant la pagination.

        Sans `pageToken`, l'API s'arrête à 250 résultats : tout ce qui suit est vu
        comme absent de Google et donc recréé à chaque run.
        """
        events: List[Dict] = []
        page_token = None

        while True:
            # Lecture idempotente : réessayable. Une page manquante ferait
            # recréer tous les événements qu'elle contenait.
            response = retry_call(
                lambda token=page_token: self.google_service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    maxResults=GOOGLE_PAGE_SIZE,
                    pageToken=token
                ).execute(),
                label="lecture du calendrier Google")

            events.extend(response.get('items', []))
            page_token = response.get('nextPageToken')

            if not page_token:
                return events

    def _index_google_events(self, google_events: List[Dict]) -> Tuple[Dict[str, Dict], List[Dict]]:
        """Indexe les événements Google par UID Exchange et isole les doublons.

        Une simple compréhension de dictionnaire écraserait les doublons : ils
        deviendraient invisibles à la synchronisation, donc jamais nettoyés.
        """
        grouped: Dict[str, List[Dict]] = {}

        for event in google_events:
            uid = get_exchange_uid(event)

            if uid:
                grouped.setdefault(uid, []).append(event)

        index, duplicates = {}, []

        for uid, events in grouped.items():
            # Tri stable par identifiant Google : la copie conservée est la même
            # d'un run à l'autre.
            events.sort(key=lambda e: e.get('id', ''))
            index[uid] = events[0]
            duplicates.extend(events[1:])

        return index, duplicates

    def _process_events(self, outlook_events: List[Dict],
                        google_index: Dict[str, Dict],
                        duplicates: List[Dict],
                        exchange_uids: Set[str],
                        window_start: datetime.datetime,
                        dry_run: bool) -> Tuple[int, int, int]:
        """Traite les événements pour synchronisation."""
        created, updated, deleted = 0, 0, 0

        # Identifiants Google rattachés à un événement Exchange de la fenêtre :
        # la passe de suppression doit les épargner, même s'ils sont indexés sous
        # une ancienne clé.
        matched_ids = set()

        # Création/mise à jour des événements
        for ev in outlook_events:
            google_event = self._prepare_google_event(ev)
            g_ev = self._find_google_event(ev, google_index)

            if g_ev is not None:
                matched_ids.add(g_ev['id'])
                changes = self._detect_changes(g_ev, ev)

                # Retrouvé via l'ancienne clé : on force l'écriture pour qu'il
                # porte désormais la nouvelle, sinon il resterait indexé à
                # l'ancienne indéfiniment.
                if get_exchange_uid(g_ev) != ev['uid']:
                    changes.append("clé")

                if changes:
                    print(f"🔁 Mise à jour ({', '.join(changes)}): {ev['subject']}")
                    if not dry_run:
                        self.google_service.events().update(
                            calendarId=self.calendar_id,
                            eventId=g_ev['id'],
                            body=google_event
                        ).execute()
                    updated += 1
            else:
                print(f"➕ Nouveau : {ev['subject']}")
                if not dry_run:
                    self.google_service.events().insert(
                        calendarId=self.calendar_id,
                        body=google_event
                    ).execute()
                created += 1

        # Suppression des doublons accumulés par les runs passés
        for g_ev in duplicates:
            print(f"➖ Doublon supprimé : {g_ev.get('summary')}")
            if self._delete(g_ev, dry_run):
                deleted += 1

        # Suppression des événements qui n'existent plus dans Exchange
        for uid, g_ev in google_index.items():
            start_dt = parse_google_start(g_ev)

            if g_ev['id'] in matched_ids or uid in exchange_uids or not start_dt:
                continue

            # En dehors de la fenêtre Exchange, on ne peut rien conclure :
            # l'absence côté Exchange ne signifie pas une suppression.
            if start_dt < window_start:
                continue

            print(f"➖ Supprimé : {g_ev.get('summary')} ({start_dt.date()})")
            if self._delete(g_ev, dry_run):
                deleted += 1

        return created, updated, deleted

    def _find_google_event(self, exchange_event: Dict,
                           google_index: Dict[str, Dict]) -> Optional[Dict]:
        """Retrouve la copie Google d'un événement Exchange.

        Le repli sur `item_id` assure la transition depuis l'ancienne clé de
        synchronisation (l'ItemId EWS) : sans lui, le changement de schéma de clé
        supprimerait et recréerait l'intégralité du calendrier au premier run.
        """
        found = google_index.get(exchange_event['uid'])

        if found is not None:
            return found

        legacy_key = exchange_event.get('item_id') or ''

        return google_index.get(legacy_key) if legacy_key else None

    def _delete(self, google_event: Dict, dry_run: bool) -> bool:
        """Supprime un événement Google. Renvoie True s'il faut le compter."""
        if dry_run:
            return True

        try:
            self.google_service.events().delete(
                calendarId=self.calendar_id,
                eventId=google_event['id']
            ).execute()
            return True
        except Exception as e:
            print(f"⚠️ Erreur suppression {google_event.get('id')}: {e}")
            return False

    def _prepare_google_event(self, exchange_event: Dict) -> Dict:
        """Prépare un événement au format Google Calendar."""
        return {
            'summary': exchange_event['subject'],
            'location': exchange_event['location'],
            'description': truncate_description(exchange_event['body']),
            'start': {
                'date': exchange_event['start'].date().isoformat()
            } if exchange_event['all_day'] else {
                'dateTime': exchange_event['start'].isoformat(),
                'timeZone': self.timezone
            },
            'end': {
                'date': exchange_event['end'].date().isoformat()
            } if exchange_event['all_day'] else {
                'dateTime': exchange_event['end'].isoformat(),
                'timeZone': self.timezone
            },
            'extendedProperties': {
                'private': {
                    'exchange_uid': exchange_event['uid']
                }
            },
        }

    def _detect_changes(self, google_event: Dict, exchange_event: Dict) -> List[str]:
        """Détecte les changements entre un événement Google et un événement Exchange."""
        g_start, g_all_day = to_utc_datetime(google_event['start'])
        g_end, _ = to_utc_datetime(google_event['end'])

        ev_start = exchange_event['start'].astimezone(datetime.timezone.utc)
        ev_end = exchange_event['end'].astimezone(datetime.timezone.utc)

        changes = []

        if g_all_day != exchange_event['all_day']:
            changes.append("type")

        if not datetimes_equal(g_start, ev_start):
            changes.append("start")

        if not datetimes_equal(g_end, ev_end):
            changes.append("end")

        if normalize_str(google_event.get('summary', '')) != normalize_str(exchange_event['subject']):
            changes.append("summary")

        if normalize_str(google_event.get('location', '')) != normalize_str(exchange_event['location']):
            changes.append("location")

        # On compare la description telle qu'elle a été ÉCRITE (tronquée), sinon un
        # corps trop long produit un écart permanent et donc un update à chaque run.
        if normalize_str(google_event.get('description', '')) != normalize_str(
                truncate_description(exchange_event['body'])):
            changes.append("description")

        return changes

    def _display_events_summary(self, events: List[Dict]) -> None:
        """Affiche un résumé des événements récupérés."""
        print(f"📄 {len(events)} événements trouvés.\n")

        for ev in events:
            if ev['all_day']:
                print(f"📅 {ev['start'].date()} | {ev['subject']} | 💤 Journée entière")
            else:
                s_local = ev['start'].astimezone(pytz.timezone(self.timezone)).strftime('%d/%m %H:%M')
                e_local = ev['end'].astimezone(pytz.timezone(self.timezone)).strftime('%H:%M')
                print(f"🗓️ {s_local} → {e_local} | {ev['subject']} | 📍 {ev['location']}")
