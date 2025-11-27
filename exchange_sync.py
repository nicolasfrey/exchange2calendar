#!/usr/bin/env python3
"""
Script de synchronisation des calendriers Exchange vers Google Calendar.

Ce script permet de synchroniser les événements d'un calendrier Exchange (Outlook Pro)
vers un calendrier Google Calendar, en créant de nouveaux événements, en mettant à jour
ceux qui ont été modifiés, et en supprimant ceux qui ont été supprimés côté Exchange.
"""

import os
import sys
import argparse
from dotenv import load_dotenv

# Import des modules du projet
from src.exchange_service import ExchangeCalendarService
from src.google_service import GoogleCalendarService
from src.synchronizer import CalendarSynchronizer
from src.utils.notification_utils import notify_error, format_exception


def main():
    """Point d'entrée principal de l'application."""
    # Chargement des variables d'environnement
    load_dotenv()

    # Récupération des paramètres d'environnement
    username = os.getenv("EXCHANGE_USERNAME")
    email = os.getenv("EXCHANGE_EMAIL")
    password = os.getenv("EXCHANGE_PASSWORD")
    google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    timezone = os.getenv("TIMEZONE", "Europe/Paris")
    days_ahead = int(os.getenv("DAYS_AHEAD", "60"))
    enable_notifications = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

    # Analyse des arguments de ligne de commande
    parser = argparse.ArgumentParser(description="Synchronise Exchange vers Google Calendar.")
    parser.add_argument("--days", type=int, default=days_ahead,
                       help=f"Nombre de jours à synchroniser (défaut: {days_ahead})")
    parser.add_argument("--dry-run", action="store_true",
                       help="Simule sans modifier le calendrier Google")
    parser.add_argument("--no-notify", action="store_true",
                       help="Désactive les notifications de bureau")

    args = parser.parse_args()

    # Désactiver les notifications si demandé par argument
    if args.no_notify:
        enable_notifications = False

    try:
        # Validation des variables d'environnement obligatoires
        if not all([username, password, email, google_calendar_id]):
            error_msg = "Configuration incomplète dans le fichier .env"
            print(f"❌ Erreur : {error_msg}")
            print("!!!Veuillez définir EXCHANGE_USERNAME, EXCHANGE_EMAIL, EXCHANGE_PASSWORD et GOOGLE_CALENDAR_ID")

            if enable_notifications:
                notify_error(error_msg)

            sys.exit(1)

        # Initialisation du service Exchange
        exchange_service = ExchangeCalendarService(
            username=username,
            email=email,
            password=password
        )

        if not exchange_service.connect():
            error_msg = "Impossible de se connecter au serveur Exchange"

            if enable_notifications:
                notify_error(error_msg)

            sys.exit(1)

        # Connexion à Google Calendar
        print("\n🔗 Connexion à Google Calendar...")
        google_service = GoogleCalendarService.authenticate()

        # Synchronisation des calendriers
        synchronizer = CalendarSynchronizer(
            exchange_service=exchange_service,
            google_service=google_service,
            calendar_id=google_calendar_id,
            timezone=timezone
        )

        synchronizer.synchronize(days_ahead=args.days, dry_run=args.dry_run)

    except Exception as e:
        error_message = f"Erreur lors de la synchronisation: {str(e)}"
        error_details = format_exception(e)

        print(f"\n❌ {error_message}")
        print(f"\nDétails: {error_details}")

        # Envoyer notification de bureau
        if enable_notifications:
            notify_error(error_message, error_details)

        # Envoyer email si configuré
        send_error_notification(error_message, error_details)

        sys.exit(1)

if __name__ == "__main__":
    main()
