"""
app.py - ממשק Streamlit. מריצים עם:  streamlit run app.py

איך Streamlit עובד: כל לחיצה על כפתור מריצה את כל הקובץ מחדש מלמעלה.
לכן:
  * את הגרף (ואיתו ה-checkpointer) יוצרים פעם אחת עם st.cache_resource,
    אחרת בכל לחיצה היה נוצר זיכרון חדש והגרף היה "שוכח" שהוא מחכה לך.
  * מה שצריך לזכור בין לחיצות (thread_id, ה-interrupt הנוכחי) שומרים ב-st.session_state.
"""
import uuid
import truststore
truststore.inject_into_ssl()
import streamlit as st
from langgraph.types import Command

from graph import build_graph
from nodes import transcribe_audio

st.set_page_config(page_title="סוכן מייל קולי", page_icon="✉️")
# כיוון מימין לשמאל לעברית
st.markdown("<style>.stApp {direction: rtl; text-align: right;}</style>", unsafe_allow_html=True)


@st.cache_resource
def get_app():
    return build_graph()


app = get_app()

# --- זיכרון בין לחיצות ---
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())  # מזהה ייחודי לכל מייל חדש
    st.session_state.pending = None   # ה-interrupt שמחכה לתשובה (או None)
    st.session_state.result = None    # התוצאה הסופית
    st.session_state.round = 0        # מונה כדי לאפס את רכיבי ההקלטה בכל סבב

config = {"configurable": {"thread_id": st.session_state.thread_id}}


def run_graph(graph_input):
    """מריץ את הגרף עד ה-interrupt הבא או עד הסוף, ושומר מה קרה."""
    with st.spinner("עובד על זה..."):
        out = app.invoke(graph_input, config)
    if "__interrupt__" in out:
        st.session_state.pending = out["__interrupt__"][0].value
    else:
        st.session_state.pending = None
        st.session_state.result = out.get("result")
    st.session_state.round += 1
    st.rerun()


def start_over():
    for key in ["thread_id", "pending", "result", "round"]:
        st.session_state.pop(key, None)
    st.rerun()


st.title("✉️ סוכן מייל קולי")

pending = st.session_state.pending

# ---------------------------------------------------------------------------
# מצב 1: התחלה - הקלטת בקשה
# ---------------------------------------------------------------------------
if pending is None and st.session_state.result is None:
    mode_label = st.radio("כשאאשר את המייל:", ["לשמור כטיוטה ב-Gmail", "לשלוח מיד"], horizontal=True)
    delivery_mode = "send" if mode_label == "לשלוח מיד" else "draft"

    st.write("הקליטי את הבקשה, למשל: *\"תכתבי למשה שהפגישה נדחתה ליום שלישי בשעה חמש\"*")
    audio = st.audio_input("הקלטה", key=f"main_audio_{st.session_state.round}")
    if audio and st.button("צור מייל", type="primary"):
        run_graph({"audio_bytes": audio.getvalue(), "delivery_mode": delivery_mode})

# ---------------------------------------------------------------------------
# מצב 2: interrupt #1 - הנמען לא נמצא
# ---------------------------------------------------------------------------
elif pending and pending["type"] == "ask_recipient":
    st.warning(f"לא מצאתי באנשי הקשר את: **{pending['heard_name'] or '(לא זוהה שם)'}**")
    options = [f"{c['name']} <{c['email']}>" for c in pending["contacts"]] + ["כתובת אחרת..."]
    choice = st.selectbox("למי לשלוח?", options)
    if choice == "כתובת אחרת...":
        name = st.text_input("שם", value=pending["heard_name"])
        email = st.text_input("כתובת מייל")
    else:
        contact = pending["contacts"][options.index(choice)]
        name, email = contact["name"], contact["email"]
    if st.button("המשך", type="primary", disabled=not email):
        run_graph(Command(resume={"name": name, "email": email}))

# ---------------------------------------------------------------------------
# מצב 3: interrupt #2 - אישור הטיוטה
# ---------------------------------------------------------------------------
elif pending and pending["type"] == "review":
    st.subheader("הטיוטה")
    st.write(f"**אל:** {pending['recipient_name']} <{pending['to']}>")
    st.write(f"**נושא:** {pending['subject']}")
    st.text_area("גוף המייל", pending["body"], height=250, disabled=True)

    col_ok, col_cancel = st.columns(2)
    if col_ok.button("✅ אשר", type="primary"):
        run_graph(Command(resume={"action": "approve"}))
    if col_cancel.button("❌ בטל"):
        run_graph(Command(resume={"action": "cancel"}))

    if pending["can_revise"]:
        st.divider()
        st.write(f"**לתקן?** (סבב {pending['revision_count'] + 1} מתוך 3) הקליטי או הקלידי מה לשנות:")
        notes_audio = st.audio_input("הערות בקול", key=f"notes_audio_{st.session_state.round}")
        notes_text = st.text_input("או הקלידי", key=f"notes_text_{st.session_state.round}")
        if st.button("🔁 תקן"):
            notes = notes_text
            if notes_audio:
                with st.spinner("מתמללת את ההערות..."):
                    notes = (transcribe_audio(notes_audio.getvalue()) + " " + notes_text).strip()
            if notes:
                run_graph(Command(resume={"action": "revise", "notes": notes}))
            else:
                st.error("צריך להקליט או להקליד מה לתקן.")
    else:
        st.info("הגעת למספר התיקונים המרבי (3). אפשר לאשר או לבטל.")

# ---------------------------------------------------------------------------
# מצב 4: סיום
# ---------------------------------------------------------------------------
else:
    st.success(st.session_state.result)
    if st.button("מייל חדש"):
        start_over()
