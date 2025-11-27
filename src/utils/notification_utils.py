"""Fonctions utilitaires pour les notifications système."""

import os
import subprocess
import traceback
from typing import Optional


def send_desktop_notification(title: str, message: str, urgency: str = "normal", icon: str = "dialog-error") -> bool:
    """
    Envoie une notification de bureau via notify-send (Linux).
    
    Args:
        title: Titre de la notification
        message: Contenu de la notification
        urgency: Niveau d'urgence ('low', 'normal', 'critical')
        icon: Icône à afficher (nom d'icône système ou chemin)
        
    Returns:
        bool: True si la notification a été envoyée, False sinon
    """
    try:
        # Vérifier si nous sommes sur un système avec un environnement graphique
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            return False
            
        # Vérifier si notify-send est disponible
        if subprocess.run(['which', 'notify-send'], stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
            return False
            
        # Envoyer la notification
        subprocess.run([
            'notify-send',
            f'--urgency={urgency}',
            f'--icon={icon}',
            title,
            message
        ])
        return True
    except Exception:
        return False


def notify_error(error_message: str, error_details: Optional[str] = None) -> None:
    """
    Envoie une notification d'erreur au bureau.
    
    Args:
        error_message: Message d'erreur principal
        error_details: Détails techniques de l'erreur (facultatif)
    """
    title = "❌ Erreur Exchange-Google Calendar"
    message = error_message
    
    if error_details:
        # Limiter les détails pour la notification
        details_preview = error_details[:100] + "..." if len(error_details) > 100 else error_details
        message += f"\n\n{details_preview}"
    
    send_desktop_notification(title, message, urgency="critical")


def format_exception(e: Exception) -> str:
    """
    Formate une exception pour l'affichage.

    Args:
        e: L'objet exception.

    Returns:
        str: Une chaîne de caractères formatée de l'exception.
    """
    return traceback.format_exc()
