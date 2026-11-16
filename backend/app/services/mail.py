"""E-mails de service (F-51). Aucun e-mail promotionnel n'est envoyé par l'application."""

import smtplib
from email.message import EmailMessage

from app.config import get_settings

# Textes en français au lancement ; une entrée par langue suffira pour traduire (section 11).
TEMPLATES: dict[str, tuple[str, str]] = {
    "verify_email": (
        "Confirmez votre adresse e-mail",
        "Bonjour,\n\nPour confirmer votre adresse et activer votre compte, ouvrez ce lien :\n{link}\n\n"
        "Le lien est valable 3 jours. Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.",
    ),
    "reset_password": (
        "Choisissez un nouveau mot de passe",
        "Bonjour,\n\nPour choisir un nouveau mot de passe, ouvrez ce lien :\n{link}\n\n"
        "Le lien est valable 1 heure. Si vous n'avez rien demandé, ignorez ce message : "
        "votre mot de passe ne change pas.",
    ),
    "magic_link": (
        "Votre lien de connexion",
        "Bonjour,\n\nPour vous connecter, ouvrez ce lien sur cet appareil :\n{link}\n\n"
        "Le lien est valable 20 minutes et ne sert qu'une fois.",
    ),
    "export_ready": (
        "Votre export est prêt",
        "Bonjour,\n\nL'archive de vos données est prête. Téléchargez-la depuis vos paramètres :\n{link}\n\n"
        "Elle reste disponible {days} jours.",
    ),
    "account_deleted": (
        "Votre compte a été supprimé",
        "Bonjour,\n\nVotre compte, vos collections, vos achats et vos photos ont été effacés. "
        "Les copies de sauvegarde disparaissent sous {days} jours.\n\nMerci d'avoir utilisé le service.",
    ),
    "series_published": (
        "La série que vous avez demandée est disponible",
        "Bonjour,\n\nLa série « {series} » vient d'être ajoutée au catalogue :\n{link}\n\n"
        "Vous pouvez la suivre dès maintenant.",
    ),
    "request_answered": (
        "Réponse à votre demande",
        "Bonjour,\n\nVotre demande « {subject} » a reçu une réponse :\n\n{reply}",
    ),
}

outbox: list[dict[str, str]] = []  # e-mails « envoyés » en développement et en test


def send(to: str, template: str, **context: object) -> None:
    settings = get_settings()
    subject, body = TEMPLATES[template]
    body = body.format(**context)
    if settings.mail_backend == "console":
        outbox.append({"to": to, "template": template, "subject": subject, "body": body})
        if settings.env == "dev":
            print(f"\n--- e-mail à {to} : {subject}\n{body}\n---")
        return

    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.mail_from, to, subject
    message.set_content(f"{body}\n\n— {settings.product_name}")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
