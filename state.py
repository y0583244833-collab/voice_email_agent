"""
state.py - ה"זיכרון" של הגרף.

ב-LangGraph כל צומת (node) מקבל את ה-State, ומחזיר מילון עם השדות שהוא רוצה לעדכן.
LangGraph ממזג את העדכון לתוך ה-State ומעביר אותו לצומת הבא.

השתמשנו ב-TypedDict (מספריית typing המובנית של Python) כי זו הדרך המקובלת
ב-LangGraph להגדיר State: פשוט, בלי ספריות נוספות, ומראה בדיוק אילו שדות קיימים.
total=False אומר שכל שדה הוא אופציונלי: בהתחלה רוב השדות עוד ריקים,
וכל צומת ממלא את החלק שלו.
"""
from typing import Literal, TypedDict


class EmailState(TypedDict, total=False):
    # --- קלט מהמשתמשת ---
    audio_bytes: bytes          # ההקלטה הגולמית מ-st.audio_input (קובץ WAV)
    delivery_mode: Literal["draft", "send"]  # המתג בממשק: טיוטה או שליחה

    # --- צומת התמלול ---
    transcript: str             # הטקסט שנאמר בהקלטה

    # --- צומת ההבנה (חילוץ) ---
    recipient_name: str         # השם כפי שנאמר, למשל "משה"
    recipient_email: str        # המייל שנמצא בקובץ אנשי הקשר
    subject: str                # נושא המייל
    key_points: list[str]       # הנקודות שצריך לכלול במייל

    # --- צומת הכתיבה ---
    draft_body: str             # גוף המייל שהמודל כתב

    # --- ה-interrupt (אדם בלולאה) ---
    review_action: Literal["approve", "revise", "cancel"]  # מה המשתמשת בחרה
    revision_notes: str         # מה לתקן, כשבוחרים "revise"
    revision_count: int         # כמה סבבי תיקון היו (כדי לעצור לולאה אינסופית)

    # --- תוצאה ---
    result: str                 # הודעה סופית: נשלח / נשמר כטיוטה / בוטל
