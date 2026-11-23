"""
llm.py - יצירת מודל ה-Gemini פעם אחת, במקום אחד.

ChatGoogleGenerativeAI היא המחלקה של LangChain (מהחבילה langchain-google-genai)
שעוטפת את Gemini. היתרון: היא מדברת ב"שפה" של LangChain (הודעות, structured output),
ולכן כל קריאה אליה נרשמת אוטומטית כ-trace ב-LangSmith.
"""
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()  # קורא את קובץ .env ומכניס את הערכים למשתני הסביבה

# temperature=0 => תשובות עקביות יותר (פחות "יצירתיות"). חשוב כשמשווים ניסויים לפני/אחרי.
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    temperature=0,
    # כמה פעמים לנסות שוב כשהשרת עמוס (שגיאה 503) או כשחורגים ממגבלת קצב (429).
    # בין ניסיון לניסיון ההמתנה מוכפלת: 1, 2, 4, 8... שניות, עד 60 שניות לכל היותר.
    max_retries=10,
)
