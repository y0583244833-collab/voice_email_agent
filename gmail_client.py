"""
gmail_client.py - שליחה / שמירת טיוטה ב-Gmail.

מצב הדמיה (DRY_RUN): כש-DRY_RUN=true בקובץ .env, שום דבר לא נשלח ל-Gmail.
הפונקציות רק מדפיסות את המייל לטרמינל. משמש לבדיקות ולהרצת הדאטהסט.

כש-DRY_RUN=false מתחברים ל-Gmail API עם OAuth:
  * credentials.json - "תעודת הזהות" של האפליקציה שלך, מורידים מ-Google Cloud Console.
  * token.json - נוצר אוטומטית אחרי שאת מאשרת בדפדפן בפעם הראשונה.
    בפעמים הבאות הקוד משתמש בו ולא שואל שוב.
  שני הקבצים פרטיים. לא משתפים ולא מעלים לשום מקום.
"""
import base64
import os
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).parent
CREDENTIALS_FILE = HERE / "credentials.json"
TOKEN_FILE = HERE / "token.json"

# הרשאה מינימלית: gmail.compose מאפשרת ליצור טיוטות ולשלוח,
# אבל לא לקרוא את המיילים שלך ולא למחוק. תמיד מבקשים את ההרשאה הקטנה ביותר שמספיקה.
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def _dry_run() -> bool:
    return os.getenv("DRY_RUN", "true").lower() == "true"


def _print_email(kind: str, to: str, subject: str, body: str) -> None:
    print(f"\n===== [DRY_RUN] {kind} =====")
    print(f"אל: {to}\nנושא: {subject}\n\n{body}")
    print("=" * 30 + "\n")


def _get_service():
    """מתחבר ל-Gmail ומחזיר אובייקט שדרכו קוראים ל-API."""
    # מייבאים כאן ולא בראש הקובץ, כדי שבמצב הדמיה לא נצטרך את ספריות Google בכלל
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())  # חידוש שקט של הכניסה, בלי דפדפן
        else:
            # פעם ראשונה: נפתח דפדפן, את מתחברת לחשבון ומאשרת
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def _build_raw(to: str, subject: str, body: str) -> dict:
    """בונה מייל בפורמט ש-Gmail מצפה לו: הודעת MIME מקודדת ב-base64."""
    msg = EmailMessage()  # ספרייה מובנית של Python; מטפלת לבד בקידוד עברית
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_email(to: str, subject: str, body: str) -> None:
    if _dry_run():
        _print_email("שליחה", to, subject, body)
        return
    _get_service().users().messages().send(userId="me", body=_build_raw(to, subject, body)).execute()


def create_draft(to: str, subject: str, body: str) -> None:
    if _dry_run():
        _print_email("טיוטה", to, subject, body)
        return
    _get_service().users().drafts().create(
        userId="me", body={"message": _build_raw(to, subject, body)}
    ).execute()
