"""
graph.py - חיבור הצמתים לגרף אחד.

מבנה הגרף:

  START -> transcribe -> extract -> lookup_contact
                                        |
                  (ענף מותנה: נמצא מייל?)
                  |                     |
                 כן                    לא
                  |                     v
                  |              ask_recipient   <- interrupt #1: בחירת נמען
                  v                     |
              write_email  <------------+
                  |
                  v
               review          <- interrupt #2: אישור / תיקון / ביטול
                  |
     (ענף מותנה לפי ההחלטה שלך)
     |              |               |
  approve        revise           cancel
     |              |               |
  deliver     write_email (לולאה!)  END
     |
    END
"""
import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

import nodes
from state import EmailState

MAX_REVISIONS = 3  # ההחלטה שלך: אחרי 3 תיקונים נשארות רק "אשר" או "בטל"


# ---------------------------------------------------------------------------
# צמתים עם interrupt (אדם בלולאה)
# ---------------------------------------------------------------------------
def ask_recipient(state: EmailState) -> dict:
    """interrupt #1: הנמען לא נמצא באנשי הקשר, אז שואלים אותך.

    interrupt(...) עוצר את הגרף באמצע הצומת, שומר את ה-State ב-checkpointer,
    ומחזיר לממשק את מה שהעברנו לו (כאן: השם שנאמר ורשימת אנשי הקשר).
    כשהממשק קורא שוב לגרף עם Command(resume=<ערך>), הגרף ממשיך בדיוק מכאן,
    ו-interrupt מחזיר את אותו <ערך>.
    """
    contacts = json.loads(nodes.CONTACTS_FILE.read_text(encoding="utf-8"))
    answer = interrupt(
        {
            "type": "ask_recipient",
            "heard_name": state.get("recipient_name", ""),
            "contacts": contacts,
        }
    )
    # answer = {"name": "...", "email": "..."}
    return {"recipient_name": answer["name"], "recipient_email": answer["email"]}


def review(state: EmailState) -> dict:
    """interrupt #2: מציג לך את הטיוטה ומחכה להחלטה."""
    count = state.get("revision_count", 0)
    decision = interrupt(
        {
            "type": "review",
            "to": state.get("recipient_email"),
            "recipient_name": state.get("recipient_name"),
            "subject": state.get("subject"),
            "body": state.get("draft_body"),
            "revision_count": count,
            "can_revise": count < MAX_REVISIONS,
        }
    )
    # decision = {"action": "approve" | "revise" | "cancel", "notes": "..."}
    update = {"review_action": decision["action"]}
    if decision["action"] == "revise":
        update["revision_notes"] = decision.get("notes", "")
        update["revision_count"] = count + 1
    return update


def deliver(state: EmailState) -> dict:
    """שולח או שומר טיוטה ב-Gmail, לפי המתג בממשק (delivery_mode)."""
    import gmail_client  # ייכתב בשלב חיבור Gmail

    mode = state.get("delivery_mode", "draft")
    if mode == "send":
        gmail_client.send_email(state["recipient_email"], state["subject"], state["draft_body"])
        return {"result": f"המייל נשלח אל {state['recipient_email']}"}
    gmail_client.create_draft(state["recipient_email"], state["subject"], state["draft_body"])
    return {"result": "המייל נשמר כטיוטה ב-Gmail"}


def cancelled(state: EmailState) -> dict:
    return {"result": "בוטל. שום מייל לא נשלח."}


# ---------------------------------------------------------------------------
# פונקציות ניתוב (router) לקשתות המותנות
# ---------------------------------------------------------------------------
def route_after_lookup(state: EmailState) -> str:
    """ענף מותנה #1: האם נמצא מייל לנמען?"""
    return "write_email" if state.get("recipient_email") else "ask_recipient"


def route_after_review(state: EmailState) -> str:
    """ענף מותנה #2 (וזו גם הלולאה): לאן ממשיכים אחרי ההחלטה שלך."""
    action = state.get("review_action")
    if action == "approve":
        return "deliver"
    if action == "cancel":
        return "cancelled"
    # revise: חוזרים לכתיבה, אלא אם עברנו את המגבלה, ואז חוזרים לשאול
    if state.get("revision_count", 0) > MAX_REVISIONS:
        return "review"
    return "write_email"


# ---------------------------------------------------------------------------
# בניית הגרף
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    builder = StateGraph(EmailState)

    builder.add_node("transcribe", nodes.transcribe)
    builder.add_node("extract", nodes.extract)
    builder.add_node("lookup_contact", nodes.lookup_contact)
    builder.add_node("ask_recipient", ask_recipient)
    builder.add_node("write_email", nodes.write_email)
    builder.add_node("review", review)
    builder.add_node("deliver", deliver)
    builder.add_node("cancelled", cancelled)

    builder.add_edge(START, "transcribe")
    builder.add_edge("transcribe", "extract")
    builder.add_edge("extract", "lookup_contact")
    builder.add_conditional_edges("lookup_contact", route_after_lookup, ["write_email", "ask_recipient"])
    builder.add_edge("ask_recipient", "write_email")
    builder.add_edge("write_email", "review")
    builder.add_conditional_edges("review", route_after_review, ["deliver", "write_email", "cancelled", "review"])
    builder.add_edge("deliver", END)
    builder.add_edge("cancelled", END)

    # checkpointer: בלעדיו interrupt לא יכול לעבוד, כי צריך לשמור את ה-State
    # בזמן שהגרף "ממתין" לך. InMemorySaver שומר בזיכרון של התוכנית, וזה מספיק לנו.
    return builder.compile(checkpointer=checkpointer or InMemorySaver())
