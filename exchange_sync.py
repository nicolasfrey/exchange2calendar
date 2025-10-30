#!/usr/bin/env python3
import os
import re
import sys
import argparse
import datetime
import pytz
from exchangelib import Credentials, Account, DELEGATE, EWSDateTime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials as GCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# ============================
# 🔐 Chargement du fichier .env
# ============================
load_dotenv()

USERNAME = os.getenv("EXCHANGE_USERNAME")
EMAIL = os.getenv("EXCHANGE_EMAIL")
PASSWORD = os.getenv("EXCHANGE_PASSWORD")
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "60"))

if not USERNAME or not PASSWORD:
    print("❌ Erreur : identifiants Exchange manquants dans le fichier .env")
    sys.exit(1)

# ============================
# 🧠 UTILITAIRES
# ============================

def load_google_service():
    """Initialise l’API Google Calendar."""
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None
    if os.path.exists('token.json'):
        creds = GCredentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def clean_subject(subject):
    """Nettoie le titre des événements Outlook (supprime [MAIL EXTERNE])."""
    if not subject:
        return 'Sans titre'
    subject = re.sub(r'\[MAIL EXTERNE\]', '', subject)
    return re.sub(r'\s+', ' ', subject).strip()

def get_exchange_uid(event):
    """Récupère l’UID Exchange stocké dans les propriétés privées Google."""
    try:
        return event.get('extendedProperties', {}).get('private', {}).get('exchange_uid', '') or event.get('description', '')
    except Exception:
        return ''

def normalize_str(s):
    """Supprime les espaces multiples et uniformise les chaînes pour la comparaison."""
    return ' '.join((s or '').split())

def to_utc_datetime(google_time):
    """Convertit une date/dateTime Google Calendar en datetime UTC + flag all_day."""
    if 'dateTime' in google_time:
        dt = datetime.datetime.fromisoformat(google_time['dateTime'].replace('Z', '+00:00'))
        return dt.astimezone(datetime.timezone.utc), False
    elif 'date' in google_time:
        d = datetime.date.fromisoformat(google_time['date'])
        return datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc), True
    return None, False

def datetimes_equal(a, b, tolerance=60):
    """Compare deux datetimes avec une tolérance (en secondes)."""
    if not a or not b:
        return False
    return abs((a - b).total_seconds()) <= tolerance

def parse_google_start(g_ev):
    """Récupère la date de début d’un événement Google."""
    start = g_ev.get('start', {})
    if 'dateTime' in start:
        s = start['dateTime'].replace('Z', '+00:00')
        return datetime.datetime.fromisoformat(s)
    elif 'date' in start:
        d = datetime.date.fromisoformat(start['date'])
        return datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)
    return None

def to_py_datetime(dt):
    """Convertit EWSDateTime/EWSDate en datetime Python timezone-aware (UTC)."""
    from exchangelib.ewsdatetime import EWSDateTime

    if isinstance(dt, EWSDateTime):
        tz = getattr(dt, "tzinfo", None)
        if tz is None:
            return dt.replace(tzinfo=pytz.UTC)
        try:
            return dt.astimezone(pytz.UTC)
        except Exception:
            return datetime.datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, tzinfo=pytz.UTC)

    elif isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        return datetime.datetime.combine(dt, datetime.time.min, tzinfo=pytz.UTC)

    elif isinstance(dt, datetime.datetime):
        return dt

    return None

# ============================
# 📦 SYNCHRONISATION
# ============================

def main(args):
    print("🔌 Connexion à Exchange...")
    creds = Credentials(username=USERNAME, password=PASSWORD)
    try:
        account = Account(primary_smtp_address=EMAIL, credentials=creds, autodiscover=True, access_type=DELEGATE)
        print(f"✅ Connecté à Exchange : {account.primary_smtp_address}")
    except Exception as e:
        print("❌ Erreur de connexion Exchange :", e)
        sys.exit(1)

    start = datetime.datetime.now(pytz.UTC)
    end = start + datetime.timedelta(days=args.days)
    print(f"📥 Lecture des événements Outlook du {start.date()} au {end.date()}...")

    outlook_events = []
    for item in account.calendar.view(start=start, end=end).order_by('start'):
        sdt = to_py_datetime(item.start)
        edt = to_py_datetime(item.end)
        if not sdt or not edt:
            continue

        all_day = isinstance(item.start, datetime.date) and not isinstance(item.start, datetime.datetime)
        ev = {
            'uid': str(item.id),
            'subject': clean_subject(item.subject),
            'location': item.location or '',
            'start': sdt,
            'end': edt,
            'all_day': all_day,
            'body': str(item.text_body) if item.text_body else '',
            'organizer': str(item.organizer.email_address) if item.organizer else '',
        }
        outlook_events.append(ev)

    print(f"📄 {len(outlook_events)} événements trouvés.\n")
    for ev in outlook_events:
        if ev['all_day']:
            print(f"📅 {ev['start'].date()} | {ev['subject']} | 💤 Journée entière")
        else:
            s_local = ev['start'].astimezone(pytz.timezone(TIMEZONE)).strftime('%d/%m %H:%M')
            e_local = ev['end'].astimezone(pytz.timezone(TIMEZONE)).strftime('%H:%M')
            print(f"🗓️ {s_local} → {e_local} | {ev['subject']} | 📍 {ev['location']}")

    if args.dry_run:
        print("\n🔎 Mode simulation (--dry-run). Aucun changement ne sera appliqué.")
        return

    print("\n🔗 Connexion à Google Calendar...")
    service = load_google_service()

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=args.days)).isoformat()

    events_result = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=now,
        timeMax=future,
        singleEvents=True
    ).execute()
    google_events = events_result.get('items', [])
    google_index = {get_exchange_uid(e): e for e in google_events}
    exchange_uids = {ev['uid'] for ev in outlook_events}

    created, updated, deleted = 0, 0, 0

    for ev in outlook_events:
        uid = ev['uid']
        google_event = {
            'summary': ev['subject'],
            'location': ev['location'],
            'description': ev['body'][:10000],
            'start': {'date': ev['start'].date().isoformat()} if ev['all_day'] else {'dateTime': ev['start'].isoformat(), 'timeZone': TIMEZONE},
            'end': {'date': ev['end'].date().isoformat()} if ev['all_day'] else {'dateTime': ev['end'].isoformat(), 'timeZone': TIMEZONE},
            'extendedProperties': {'private': {'exchange_uid': uid}},
        }

        if uid in google_index:
            g_ev = google_index[uid]
            g_start, g_all_day = to_utc_datetime(g_ev['start'])
            g_end, _ = to_utc_datetime(g_ev['end'])
            ev_start = ev['start'].astimezone(datetime.timezone.utc)
            ev_end = ev['end'].astimezone(datetime.timezone.utc)

            changes = []
            if g_all_day != ev['all_day']:
                changes.append("type")
            if not datetimes_equal(g_start, ev_start):
                changes.append("start")
            if not datetimes_equal(g_end, ev_end):
                changes.append("end")
            if normalize_str(g_ev.get('summary', '')) != normalize_str(ev['subject']):
                changes.append("summary")
            if normalize_str(g_ev.get('location', '')) != normalize_str(ev['location']):
                changes.append("location")
            if normalize_str(g_ev.get('description', '')) != normalize_str(ev['body']):
                changes.append("description")

            if changes:
                print(f"🔁 Mise à jour ({', '.join(changes)}): {ev['subject']}")
                if not args.dry_run:
                    service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=g_ev['id'], body=google_event).execute()
                updated += 1
        else:
            print(f"➕ Nouveau : {ev['subject']}")
            if not args.dry_run:
                service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=google_event).execute()
            created += 1

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for g_ev in google_events:
        uid = get_exchange_uid(g_ev)
        start_dt = parse_google_start(g_ev)
        if uid and uid not in exchange_uids and start_dt and start_dt > now_utc:
            if args.dry_run:
                print(f"[dry-run] ➖ supprimerait: {g_ev.get('summary')} ({uid}) à {start_dt.date()}")
            else:
                try:
                    service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=g_ev['id']).execute()
                    deleted += 1
                except Exception as e:
                    print(f"⚠️ Erreur suppression {g_ev.get('id')}: {e}")

    print(f"\n✅ Synchronisation terminée : {created} créés, {updated} mis à jour, {deleted} supprimés.")

# ============================
# 🚀 POINT D'ENTRÉE
# ============================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronise Exchange vers Google Calendar.")
    parser.add_argument("--days", type=int, default=DAYS_AHEAD, help="Nombre de jours à synchroniser (défaut: 60)")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans modifier le calendrier Google")
    args = parser.parse_args()
    main(args)