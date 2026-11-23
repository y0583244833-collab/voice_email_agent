"""
nodes.py - הצמתים (nodes) של הגרף.

כל צומת הוא פונקציית Python רגילה:
  מקבלת את ה-State  ->  מחזירה מילון עם השדות שהיא מעדכנת בלבד.
"""
import base64
import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from llm import llm
from state import EmailState

CONTACTS_FILE = Path(__file__).parent / "contacts.json"


# ---------------------------------------------------------------------------
# 1. תמלול: קול -> טקסט
# ---------------------------------------------------------------------------
def transcribe_audio(audio_bytes: bytes) -> str:
    """שולח קובץ שמע ל-Gemini ומחזיר תמלול מדויק.

    Gemini הוא מודל multimodal: הוא מקבל באותה הודעה גם קטע שמע וגם טקסט.
    ב-LangChain מעבירים שמע כ"content block" מסוג audio, מקודד ב-base64
    (base64 = דרך לייצג קובץ בינארי כטקסט, כדי שאפשר יהיה לשלוח אותו ב-JSON).
    הפונקציה נפרדת מהצומת כדי שהממשק יוכל להשתמש בה גם לתמלול הערות תיקון.
    """
    audio_b64 = base64.b64encode(audio_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "audio", "base64": audio_b64, "mime_type": "audio/wav"},
            {
                "type": "text",
                "text": "תמלל/י את ההקלטה מילה במילה, בשפה שבה דוברו. "
                "החזר/י רק את התמלול, בלי הקדמות.",
            },
        ]
    )
    return llm.invoke([message]).text.strip()


def transcribe(state: EmailState) -> dict:
    """צומת התמלול: לוקח את ההקלטה מה-State ושומר את הטקסט."""
    return {"transcript": transcribe_audio(state["audio_bytes"])}


# ---------------------------------------------------------------------------
# 2. הבנה: טקסט חופשי -> נתונים מובנים
# ---------------------------------------------------------------------------
class EmailRequest(BaseModel):
    """המבנה שאנחנו רוצים שהמודל יחזיר.

    with_structured_output (ראו למטה) מכריח את המודל להחזיר אובייקט בדיוק במבנה הזה,
    במקום טקסט חופשי שהיינו צריכים לפרק לבד. Field(description=...) הוא ההסבר
    שהמודל רואה לכל שדה.
    """
    recipient_name: str = Field(description="שם הנמען כפי שנאמר בבקשה, למשל 'משה' או 'הוועד'")
    subject: str = Field(description="נושא קצר למייל, עד 8 מילים")
    key_points: list[str] = Field(description="הנקודות שהמייל חייב לכלול, כל נקודה משפט קצר")


extractor = llm.with_structured_output(EmailRequest)


def extract(state: EmailState) -> dict:
    """מחלץ מהתמלול: למי, על מה, ומה לכתוב."""
    result: EmailRequest = extractor.invoke(
        [
            SystemMessage(
                "את/ה עוזר/ת שמבין/ה בקשות קוליות לכתיבת מייל. "
                "חלץ/י מהבקשה את שם הנמען, נושא ונקודות עיקריות."
            ),
            HumanMessage(state["transcript"]),
        ]
    )
    return {
        "recipient_name": result.recipient_name,
        "subject": result.subject,
        "key_points": result.key_points,
    }


# ---------------------------------------------------------------------------
# 3. חיפוש איש קשר: קוד Python רגיל, בלי מודל
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    return text.strip().lower()


def lookup_contact(state: EmailState) -> dict:
    """מחפש את השם שנאמר ב-contacts.json (לפי שם מלא או כינוי).

    למה בקוד ולא במודל? כי כתובת מייל חייבת להיות מדויקת. המודל עלול
    "להמציא" כתובת, וקוד פשוט אף פעם לא ממציא. אם לא נמצא, מחזירים מחרוזת ריקה,
    והקשת המותנית בגרף תחליט מה לעשות.
    """
    contacts = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
    wanted = _normalize(state.get("recipient_name", ""))
    for contact in contacts:
        names = [contact["name"], *contact.get("aliases", [])]
        if any(_normalize(n) == wanted for n in names):
            return {"recipient_email": contact["email"], "recipient_name": contact["name"]}
    return {"recipient_email": ""}


# ---------------------------------------------------------------------------
# 4. כתיבת המייל (וגם כתיבה מחדש אחרי בקשת תיקון)
# ---------------------------------------------------------------------------
def write_email(state: EmailState) -> dict:
    """כותב את גוף המייל. אם יש הערות תיקון, משכתב לפיהן את הטיוטה הקודמת.

    זה הצומת שהלולאה חוזרת אליו: interrupt -> "revise" -> write_email -> interrupt ...
    """
    points = "\n".join(f"- {p}" for p in state.get("key_points", []))
    # --- השיפור (ניסוי "after") ---
    # לפני: ביקשנו רק "פתיחה, תוכן, סיום", והמודל "מילא" - מיילים ארוכים פי 3.4 מהבקשה,
    # תוכן שלא נאמר ו-[השם שלך]. עכשיו: נותנים לו את הבקשה המקורית, אוסרים במפורש
    # להוסיף, ונותנים מגבלת אורך מספרית.
    prompt = (
        "כתוב/כתבי מייל קצר בעברית, בשפה מכובדת ונקייה.\n"
        "- כתוב/כתבי רק את מה שנאמר בבקשה. אל תוסיף/י פרטים, הסברים או בקשות שלא נאמרו.\n"
        "- אורך: עד פי 2 מהבקשה. בקשה של משפט אחד = מייל של 1-2 משפטים.\n"
        f'- פתיחה: "שלום {state.get("recipient_name")}," וסיום: "תודה". '
        "בלי חתימה ובלי סוגריים למילוי כמו [השם שלך].\n\n"
        f"הבקשה כפי שנאמרה:\n{state.get('transcript', '')}\n\n"
        f"נקודות שחייבות להופיע:\n{points}\n\n"
        "החזר/י רק את גוף המייל, בלי שורת נושא."
    )
    notes = state.get("revision_notes")
    if notes and state.get("draft_body"):
        prompt += (
            f"\n\nזו הטיוטה הקודמת:\n{state['draft_body']}\n\n"
            f"תקן/י אותה לפי ההערות הבאות:\n{notes}"
        )
    response = llm.invoke([HumanMessage(prompt)])
    return {"draft_body": response.text.strip()}
