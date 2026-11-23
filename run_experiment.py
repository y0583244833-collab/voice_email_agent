"""
run_experiment.py - מריץ ניסוי ב-LangSmith.

  python run_experiment.py before     <- לפני השיפור
  python run_experiment.py after      <- אחרי השיפור

evaluate() לוקח כל דוגמה מהדאטהסט, מריץ עליה את target, ואז מריץ כל מעריך.
התוצאות נשמרות ב-LangSmith תחת Datasets & Experiments ⬅ voice-email-requests.
"""
import sys

from dotenv import load_dotenv
from langsmith import evaluate
from pydantic import BaseModel, Field

load_dotenv()

import nodes  # noqa: E402  (אחרי load_dotenv כדי שהמפתחות כבר ייטענו)
from llm import llm  # noqa: E402

DATASET_NAME = "voice-email-requests"


# ---------------------------------------------------------------------------
# target: החלק בגרף שאנחנו בודקים (בלי interrupt, כי בניסוי אין מי שיאשר)
# ---------------------------------------------------------------------------
def target(inputs: dict) -> dict:
    state = {"transcript": inputs["request"]}
    state.update(nodes.extract(state))
    state.update(nodes.lookup_contact(state))
    state.update(nodes.write_email(state))
    return {
        "recipient_email": state.get("recipient_email", ""),
        "subject": state.get("subject", ""),
        "email_body": state.get("draft_body", ""),
    }


# ---------------------------------------------------------------------------
# מעריך 1 (קוד): נמען נכון
# כל מעריך מקבל: inputs (הבקשה), outputs (מה ה-target החזיר),
# reference_outputs (התשובה הנכונה מהדאטהסט), ומחזיר מילון עם key ו-score.
# ---------------------------------------------------------------------------
def correct_recipient(outputs: dict, reference_outputs: dict) -> dict:
    # .get ולא [...]: אם ה-target נכשל (למשל שגיאת שרת), outputs ריק, וזה ציון 0 ולא קריסה
    ok = outputs.get("recipient_email") == reference_outputs["recipient_email"]
    return {"key": "correct_recipient", "score": int(ok)}


# ---------------------------------------------------------------------------
# מעריך 2 (קוד): יחס אורך = מילים במייל / מילים בבקשה. נמוך יותר = צמוד יותר.
# ---------------------------------------------------------------------------
def length_ratio(inputs: dict, outputs: dict) -> dict:
    if not outputs.get("email_body"):
        return {"key": "length_ratio", "score": None, "comment": "ה-target נכשל, אין מייל למדוד"}
    request_words = max(len(inputs["request"].split()), 1)
    email_words = len(outputs["email_body"].split())
    return {"key": "length_ratio", "score": round(email_words / request_words, 2)}


# ---------------------------------------------------------------------------
# מעריך 3 (LLM-as-judge): האם המייל נאמן למה שנאמר?
# ---------------------------------------------------------------------------
class FaithfulnessVerdict(BaseModel):
    reasoning: str = Field(description="הסבר קצר: מה נוסף או חסר במייל ביחס לבקשה")
    added_content: bool = Field(description="True אם המייל מוסיף תוכן מהותי שלא נאמר בבקשה")
    missing_points: bool = Field(description="True אם חסרה במייל אחת מהנקודות הנדרשות")


judge = llm.with_structured_output(FaithfulnessVerdict)


def faithfulness(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    if not outputs.get("email_body"):
        return {"key": "faithfulness", "score": None, "comment": "ה-target נכשל, אין מייל לשפוט"}
    points = "\n".join(f"- {p}" for p in reference_outputs["key_points"])
    verdict: FaithfulnessVerdict = judge.invoke(
        "את/ה בודק/ת מיילים. השווה/י בין הבקשה למייל שנכתב.\n"
        "ברכת פתיחה וסיום קצרה אינן נחשבות תוכן נוסף.\n\n"
        f"הבקשה:\n{inputs['request']}\n\n"
        f"נקודות שחייבות להופיע:\n{points}\n\n"
        f"המייל שנכתב:\n{outputs['email_body']}"
    )
    score = int(not verdict.added_content and not verdict.missing_points)
    return {"key": "faithfulness", "score": score, "comment": verdict.reasoning}


if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else "before"
    evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[correct_recipient, length_ratio, faithfulness],
        experiment_prefix=prefix,
        max_concurrency=1,  # קריאה אחת בכל פעם, כדי לא לחרוג ממגבלת הבקשות בחינם
    )
    print("הניסוי הסתיים. התוצאות ב-LangSmith: Datasets & Experiments ⬅ voice-email-requests")
