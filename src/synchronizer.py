"""Gestion de la synchronisation entre Exchange et Google Calendar."""

import datetime
from typing import Dict, List, Tuple, Any, Set

import pytz

from src.utils.datetime_utils import (
    to_utc_datetime, normalize_str, datetimes_equal, parse_google_start
)
from src.google_service import get_exchange_uid


class CalendarSynchronizer:
    """Gère la synchronisation entre Exchange et Google Calendar."""

    def __init__(self, exchange_service: Any, google_service: Any, calendar_id: str, timezone: str):
        """Initialise le synchronisateur."""
        self.exchange_service = exchange_service
        self.google_service = google_service
        self.calendar_id = calendar_id
        self.timezone = timezone

    def synchronize(self, days_ahead: int, dry_run: bool = False) -> Tuple[int, int, int]:
        """Synchronise les événements entre Exchange et Google Calendar."""
        # Périodes de synchronisation
        start = datetime.datetime.now(pytz.UTC)
        end = start + datetime.timedelta(days=days_ahead)

        print(f"📥 Lecture des événements Outlook du {start.date()} au {end.date()}...")

        # Récupération des événements Exchange
        outlook_events = self.exchange_service.get_events(start, end)

        # Affichage des événements récupérés
        self._display_events_summary(outlook_events)

        if dry_run:
            print("\n🔎 Mode simulation (--dry-run). Aucun changement ne sera appliqué.")
            return 0, 0, 0

        # Récupération des événements Google
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_ahead)).isoformat()

        print("\n🔗 Connexion à Google Calendar...")

        events_result = self.google_service.events().list(
            calendarId=self.calendar_id,
            timeMin=now_utc,
            timeMax=future,
            singleEvents=True
        ).execute()

        google_events = events_result.get('items', [])

        # Création d'un index des événements Google par UID Exchange
        google_index = {get_exchange_uid(e): e for e in google_events}
        exchange_uids = {ev['uid'] for ev in outlook_events}

        created, updated, deleted = self._process_events(outlook_events, google_index, exchange_uids, dry_run)

        print(f"\n✅ Synchronisation terminée : {created} créés, {updated} mis à jour, {deleted} supprimés.")
        return created, updated, deleted

    def _process_events(self, outlook_events: List[Dict],
                       google_index: Dict[str, Dict],
                       exchange_uids: Set[str],
                       dry_run: bool) -> Tuple[int, int, int]:
        """Traite les événements pour synchronisation."""
        created, updated, deleted = 0, 0, 0

        # Création/mise à jour des événements
        for ev in outlook_events:
            uid = ev['uid']
            google_event = self._prepare_google_event(ev)

            if uid in google_index:
                # Mise à jour d'un événement existant
                g_ev = google_index[uid]
                changes = self._detect_changes(g_ev, ev)

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
                # Création d'un nouvel événement
                print(f"➕ Nouveau : {ev['subject']}")
                if not dry_run:
                    self.google_service.events().insert(
                        calendarId=self.calendar_id,
                        body=google_event
                    ).execute()
                created += 1

        # Suppression des événements qui n'existent plus dans Exchange
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for g_ev in google_index.values():
            uid = get_exchange_uid(g_ev)
            start_dt = parse_google_start(g_ev)

            if uid and uid not in exchange_uids and start_dt and start_dt > now_utc:
                if dry_run:
                    print(f"[dry-run] ➖ supprimerait: {g_ev.get('summary')} ({uid}) à {start_dt.date()}")
                else:
                    try:
                        self.google_service.events().delete(
                            calendarId=self.calendar_id,
                            eventId=g_ev['id']
                        ).execute()
                        deleted += 1
                    except Exception as e:
                        print(f"⚠️ Erreur suppression {g_ev.get('id')}: {e}")

        return created, updated, deleted

    def _prepare_google_event(self, exchange_event: Dict) -> Dict:
        """Prépare un événement au format Google Calendar."""
        return {
            'summary': exchange_event['subject'],
            'location': exchange_event['location'],
            'description': exchange_event['body'][:10000],
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

        if normalize_str(google_event.get('description', '')) != normalize_str(exchange_event['body']):
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
