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

    # Validation des variables d'environnement obligatoires
    if not all([username, password, email, google_calendar_id]):
        print("❌ Erreur : configuration incomplète dans le fichier .env")
        print("Veuillez définir EXCHANGE_USERNAME, EXCHANGE_EMAIL, EXCHANGE_PASSWORD et GOOGLE_CALENDAR_ID")
        sys.exit(1)

    # Analyse des arguments de ligne de commande
    parser = argparse.ArgumentParser(description="Synchronise Exchange vers Google Calendar.")
    parser.add_argument("--days", type=int, default=days_ahead,
                       help=f"Nombre de jours à synchroniser (défaut: {days_ahead})")
    parser.add_argument("--dry-run", action="store_true",
                       help="Simule sans modifier le calendrier Google")

    args = parser.parse_args()

    # Initialisation du service Exchange
    exchange_service = ExchangeCalendarService(
        username=username,
        email=email,
        password=password
    )

    if not exchange_service.connect():
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


if __name__ == "__main__":
    main()
