"""Fonctions utilitaires pour la manipulation des dates."""

import datetime
import pytz
from typing import Dict, Optional, Tuple, Any
from exchangelib.ewsdatetime import EWSDateTime


def normalize_str(s: Optional[str]) -> str:
    """Normalise une chaîne pour comparaison."""
    return ' '.join((s or '').split())


def to_utc_datetime(google_time: Dict) -> Tuple[Optional[datetime.datetime], bool]:
    """Convertit une date/heure Google Calendar en datetime UTC."""
    if 'dateTime' in google_time:
        dt = datetime.datetime.fromisoformat(google_time['dateTime'].replace('Z', '+00:00'))
        return dt.astimezone(datetime.timezone.utc), False

    elif 'date' in google_time:
        d = datetime.date.fromisoformat(google_time['date'])
        return datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc), True

    return None, False


def datetimes_equal(a: Optional[datetime.datetime], b: Optional[datetime.datetime],
                   tolerance: int = 60) -> bool:
    """Compare deux datetimes avec une tolérance en secondes."""
    if not a or not b:
        return False

    return abs((a - b).total_seconds()) <= tolerance


def parse_google_start(g_ev: Dict) -> Optional[datetime.datetime]:
    """Récupère la date de début d'un événement Google."""
    start = g_ev.get('start', {})

    if 'dateTime' in start:
        s = start['dateTime'].replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(s)

    elif 'date' in start:
        d = datetime.date.fromisoformat(start['date'])
        return datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)

    return None


def to_py_datetime(dt: Any) -> Optional[datetime.datetime]:
    """Convertit un objet de date Exchange en datetime Python."""
    if isinstance(dt, EWSDateTime):
        tz = getattr(dt, "tzinfo", None)

        if tz is None:
            return dt.replace(tzinfo=pytz.UTC)

        try:
            return dt.astimezone(pytz.UTC)
        except Exception:
            # Fallback pour les problèmes de conversion de timezone
            return datetime.datetime(
                dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second,
                tzinfo=pytz.UTC
            )

    elif isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        # Date simple (sans heure) → datetime à minuit UTC
        return datetime.datetime.combine(dt, datetime.time.min, tzinfo=pytz.UTC)

    elif isinstance(dt, datetime.datetime):
        # Déjà un datetime Python
        return dt

    return None
