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
from src.utils.healthchecks_utils import send_healthcheck_ping


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
    parser.add_argument("--no-healthcheck", action="store_true",
                       help="Désactive les pings healthchecks.io")

    args = parser.parse_args()

    # Désactiver les notifications si demandé par argument
    if args.no_notify:
        enable_notifications = False

    # Envoyer un ping de début si healthchecks est activé
    if not args.no_healthcheck:
        send_healthcheck_ping("start")

    try:
        # Validation des variables d'environnement obligatoires
        if not all([username, password, email, google_calendar_id]):
            error_msg = "Configuration incomplète dans le fichier .env"
            print(f"❌ Erreur : {error_msg}")
            print("!!!Veuillez définir EXCHANGE_USERNAME, EXCHANGE_EMAIL, EXCHANGE_PASSWORD et GOOGLE_CALENDAR_ID")

            if enable_notifications:
                notify_error(error_msg)

            if not args.no_healthcheck:
                send_healthcheck_ping("fail", error_msg)

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

            if not args.no_healthcheck:
                send_healthcheck_ping("fail", error_msg)

            sys.exit(1)

        # Connexion à Google Calendar
        print("\n Connexion à Google Calendar...")
        try:
            google_service = GoogleCalendarService.authenticate()
        except Exception as e:
            error_msg = "Erreur d'authentification Google Calendar"
            error_details = format_exception(e)
            print(f"\n❌ {error_msg}")
            print(f"\nDétails: {error_details}")
            print("\nConseil: Supprimez le fichier token.json et réessayez pour vous authentifier à nouveau.")

            if enable_notifications:
                notify_error(error_msg, "Token expiré ou révoqué. Supprimez token.json et réessayez.")

            if not args.no_healthcheck:
                send_healthcheck_ping("fail", f"{error_msg}\n\n{error_details}")

            sys.exit(1)

        # Synchronisation des calendriers
        synchronizer = CalendarSynchronizer(
            exchange_service=exchange_service,
            google_service=google_service,
            calendar_id=google_calendar_id,
            timezone=timezone
        )

        created, updated, deleted = synchronizer.synchronize(days_ahead=args.days, dry_run=args.dry_run)

        # Envoyer un ping de succès avec les statistiques
        if not args.no_healthcheck:
            success_msg = f"Synchronisation réussie: {created} créés, {updated} mis à jour, {deleted} supprimés"
            send_healthcheck_ping("success", success_msg)

    except Exception as e:
        error_message = f"Erreur lors de la synchronisation: {str(e)}"
        error_details = format_exception(e)

        print(f"\n❌ {error_message}")
        print(f"\nDétails: {error_details}")

        # Envoyer notification de bureau
        if enable_notifications:
            notify_error(error_message, error_details)

        # Envoyer un ping d'échec à healthchecks.io
        if not args.no_healthcheck:
            send_healthcheck_ping("fail", f"{error_message}\n\n{error_details}")

        sys.exit(1)


if __name__ == "__main__":
    main()
