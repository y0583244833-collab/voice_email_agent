"""
create_dataset.py - מעלה את הדאטהסט ל-LangSmith. מריצים פעם אחת:  python create_dataset.py

Client() הוא החיבור ל-LangSmith. הוא קורא לבד את LANGSMITH_API_KEY מה-.env.
"""
import json
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

DATASET_NAME = "voice-email-requests"
EXAMPLES_FILE = Path(__file__).parent / "dataset_examples.json"

client = Client()

if client.has_dataset(dataset_name=DATASET_NAME):
    # לא יוצרים פעמיים: "לפני" ו"אחרי" חייבים לרוץ על אותו דאטהסט בדיוק
    print(f"הדאטהסט '{DATASET_NAME}' כבר קיים. לא נוגעים בו.")
else:
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="בקשות קוליות (כטקסט בסגנון דיבור) לכתיבת מייל, עם הנמען והנקודות הצפויים",
    )
    examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    # כל דוגמה: inputs = מה נכנס, outputs = התשובה הנכונה (reference) שהמעריכים משווים אליה
    client.create_examples(dataset_id=dataset.id, examples=examples)
    print(f"נוצר הדאטהסט '{DATASET_NAME}' עם {len(examples)} דוגמאות.")
