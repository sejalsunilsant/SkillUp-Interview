"""
app.py  –  SkillUp Interview Platform
=======================================
Updated to use Python-side real-time emotion detection (EmotionDetector)
instead of the JavaScript posture heuristic.

Key changes vs original:
  • /start-session  → starts the EmotionDetector background thread
  • /emotion-status → live polling endpoint (replaces JS posture polling)
  • /evaluate       → calls detector.get_session_summary() for posture_data
  • /stop-session   → stops the detector cleanly
"""

# Silence TF/oneDNN logs before any TF import
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_cors import CORS
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from datetime import datetime
import uuid
import bcrypt
from functools import wraps

# ── Emotion Detector ──────────────────────────────────────────────────────────
from emotion_detector import EmotionDetector

# ── DB helper (unchanged) ─────────────────────────────────────────────────────
from database_con import get_db_connection

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.getenv("FLASK_SECRET_KEY", "skillup_secret_key")

# ── LLM ───────────────────────────────────────────────────────────────────────
llm = ChatGroq(
    groq_api_key=os.getenv("groq_Api"),
    model_name="llama-3.1-8b-instant",
    temperature=0.7,
)

# ── Global emotion detector instance ─────────────────────────────────────────
#    One detector is shared across all interview sessions on this server.
#    For multi-user production deployments, move this into a per-session object.
emotion_detector: EmotionDetector = EmotionDetector(   
    smooth_window=10,
    min_confidence=0.40,
)



# ============================================================
# INTERVIEW SESSION MODEL
# ============================================================
class InterviewSession:
    def __init__(self, question_text, topic, difficulty_level):
        self.session_id       = str(uuid.uuid4())
        self.question_text    = question_text
        self.user_transcription = None
        self.topic            = topic
        self.difficulty_level = difficulty_level
        self.timestamp        = datetime.utcnow().isoformat()
        self.posture_data     = None   # filled at evaluate time
        self.feedback         = None
        self.emotion_history = []


    def to_dict(self):
        return {
            "session_id":         self.session_id,
            "question_text":      self.question_text,
            "user_transcription": self.user_transcription,
            "topic":              self.topic,
            "difficulty_level":   self.difficulty_level,
            "timestamp":          self.timestamp,
            "posture_data":       self.posture_data,
            "feedback":           self.feedback,
        }


sessions: dict[str, InterviewSession] = {}


# ============================================================
# PASSWORD UTILS  (unchanged)
# ============================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def check_password(plain_pw: str, hashed_pw: str) -> bool:
    try:
        return bcrypt.checkpw(plain_pw.encode("utf-8"), hashed_pw.encode("utf-8"))
    except ValueError:
        return False


# ============================================================
# AUTH DECORATOR  (unchanged)
# ============================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# AUTH ROUTES  (unchanged)
# ============================================================
@app.route("/", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():
    data     = request.get_json()
    name     = data.get("name")
    email    = data.get("email")
    password = data.get("password")

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Email already registered"})

        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed_pw),
        )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(e)
        return jsonify({"success": False, "message": "Server error"})
    finally:
        cursor.close()
        conn.close()


@app.route("/login", methods=["POST"])
def api_login():
    data     = request.json
    email    = data.get("email")
    password = data.get("password")

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT user_id, name, email, password FROM users WHERE email = %s", (email,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password(password, user["password"]):
        session["user_id"] = user["user_id"]
        session["name"]    = user["name"]
        return jsonify({"message": "Login successful"}), 200

    return jsonify({"error": "Invalid email or password"}), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ============================================================
# PROTECTED INTERVIEW PAGE
# ============================================================
@app.route("/interview")
@login_required
def interview_page():
    return render_template("interview.html")


# ============================================================
# NEW ► START SESSION  (starts emotion detector)
# ============================================================
@app.route("/start-session", methods=["POST"])
def start_session():
    """
    Call this when the candidate clicks 'Start Interview'.
    Boots the EmotionDetector background thread if not already running.
    """
    if not emotion_detector.is_running():
        try:
            emotion_detector.start()
            return jsonify({"success": True, "message": "Emotion detector started"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    return jsonify({"success": True, "message": "Emotion detector already running"})


# ============================================================
# NEW ► LIVE EMOTION STATUS  (replaces JS posture polling)
# ============================================================
@app.route("/emotion-status", methods=["GET"])
def emotion_status():
    """
    Frontend polls this every ~500 ms to display live emotion data.
    Returns JSON compatible with the existing status-badge UI.
    """
    if not emotion_detector.is_running():
        return jsonify({
            "emotion":       "N/A",
            "confidence":    0.0,
            "face_detected": False,
            "stability":     "Inactive",
            "notes":         "Detector not started",
        })

    data = emotion_detector.get_current_emotion()
    return jsonify({
        "emotion":           data["emotion"],
        "confidence":        round(data["confidence"] * 100, 1),   # % for display
        "face_detected":     data["face_detected"],
        "stability":         data["stability"],
        "dominant_emotion":  data.get("dominant_emotion", "N/A"),
        "emotion_summary":   data.get("emotion_summary", {}),
        "all_probabilities": data.get("all_probabilities", {}),
        "notes":             data["notes"],
        "duration":          data.get("duration", 0),
    })
import base64
import numpy as np
import cv2
@app.route("/detect-emotion", methods=["POST"])
def detect_emotion():

    data = request.json["image"]

    image_data = base64.b64decode(data.split(",")[1])

    np_arr = np.frombuffer(image_data, np.uint8)

    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    result = emotion_detector.process_frame(frame)

    return jsonify(result)
# ============================================================
# STEP 1: Generate HR Question & Create Session  (unchanged)
# ============================================================
@app.route("/hr-questions", methods=["POST"])
def hr_questions():
    data       = request.json
    level      = data.get("level", "easy")
    count      = data.get("count", 1)
    topic      = data.get("topic", "Technical")

    prompt = f"""
    You are an experienced HR interviewer conducting a {level}-level interview.
    Generate {count} {level}-level interview question related to: {topic}
    The question should assess practical application related to the topic.
    Return ONLY the question text, nothing else.
    """

    try:
        result   = llm.invoke(prompt)
        question = result.content if hasattr(result, "content") else str(result)

        interview_session = InterviewSession(
            question_text=question.strip(),
            topic=topic,
            difficulty_level=level,
        )
        sessions[interview_session.session_id] = interview_session

        return jsonify({
            "session_id":       interview_session.session_id,
            "question":         interview_session.question_text,
            "topic":            interview_session.topic,
            "difficulty_level": interview_session.difficulty_level,
            "timestamp":        interview_session.timestamp,
        })

    except Exception as e:
        print("HR QUESTIONS ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ============================================================
# STEP 2-4: Evaluate Response  (now uses EmotionDetector data)
# ============================================================
@app.route("/evaluate", methods=["POST"])
def evaluate():
    """
    Context-aware evaluation using complete session + emotion data.
    posture_data is now supplied by the Python EmotionDetector,
    but the frontend can still send its own posture_data as override/fallback.
    """
    data        = request.json
    session_id  = data.get("session_id")
    transcript  = data.get("transcript", "")
    # Frontend posture_data is accepted as a fallback
    frontend_posture = data.get("posture_data", {})

    if not transcript.strip():
        return jsonify({"error": "Empty transcript"}), 400

    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400

    interview_session = sessions[session_id]
    interview_session.user_transcription = transcript

    # ── Merge emotion data from Python detector ───────────────────────────────
    if emotion_detector.is_running():
        emotion_summary = emotion_detector.get_session_summary()
    else:
        # Graceful fallback: use whatever the frontend sent
        emotion_summary = {
            "duration":         frontend_posture.get("duration", 0),
            "stability":        frontend_posture.get("stability", "Unknown"),
            "notes":            frontend_posture.get("notes", "Emotion detector not running"),
            "emotion":          "Unknown",
            "dominant_emotion": "Unknown",
            "emotion_summary":  {},
        }

    interview_session.posture_data = emotion_summary

    # ── Structured payload for LLM ───────────────────────────────────────────
    structured_payload = {
        "session_id":       interview_session.session_id,
        "question_text":    interview_session.question_text,
        "user_transcription": interview_session.user_transcription,
        "topic":            interview_session.topic,
        "difficulty_level": interview_session.difficulty_level,
        "timestamp":        interview_session.timestamp,
        "posture_data": {
            "duration":         emotion_summary.get("duration", 0),
            "stability":        emotion_summary.get("stability", "Unknown"),
            "notes":            emotion_summary.get("notes", "Not available"),
            # NEW emotion fields
            "current_emotion":  emotion_summary.get("emotion", "Unknown"),
            "dominant_emotion": emotion_summary.get("dominant_emotion", "Unknown"),
            "emotion_summary":  emotion_summary.get("emotion_summary", {}),
        },
    }

    # ── Evaluation prompt (enriched with emotion context) ─────────────────────
    emotion_section = ""
    if emotion_summary.get("emotion_summary"):
        breakdown = ", ".join(
            f"{e}: {p}%" for e, p in emotion_summary["emotion_summary"].items()
        )
        emotion_section = f"- Emotion Breakdown: {breakdown}"

    prompt = f"""
        You are an expert interview coach providing detailed, professional feedback.

        STRUCTURED INTERVIEW SESSION DATA:
        Session ID: {structured_payload['session_id']}
        Topic: {structured_payload['topic']}
        Difficulty Level: {structured_payload['difficulty_level']}
        Timestamp: {structured_payload['timestamp']}

        INTERVIEW QUESTION:
        {structured_payload['question_text']}

        CANDIDATE'S ANSWER (Speech-to-Text):
        {structured_payload['user_transcription']}

        POSTURE & EMOTION DATA (detected by Python AI):
        - Duration: {structured_payload['posture_data']['duration']} seconds
        - Stability: {structured_payload['posture_data']['stability']}
        - Current Emotion: {structured_payload['posture_data']['current_emotion']}
        - Dominant Emotion: {structured_payload['posture_data']['dominant_emotion']}
        {emotion_section}
        - Notes: {structured_payload['posture_data']['notes']}

        Please provide structured feedback in the following format:

        ## Interview Question (Restated)
        [Clearly restate the interview question]

        ## Overall Assessment
        [Provide a brief overall evaluation – 2–3 sentences]

        ## Content Analysis (Answer Quality)
        - Relevance: [How well did they address the question?]
        - Depth: [Did they provide sufficient detail and examples?]
        - Structure: [Was the answer well-organized?]

        ## Communication Skills
        - Clarity: [Was the answer clear and easy to understand?]
        - Confidence: [Based on word choice and phrasing]
        - Professionalism: [Appropriate language and tone?]

        ## Emotional Presence & Body Language
        - Dominant Emotion Detected: [{structured_payload['posture_data']['dominant_emotion']}]
        - Stability: [Comment on their emotional consistency during the interview]
        - Engagement: [Based on duration and emotional range detected]
        - Coaching Tip: [One specific tip based on their detected emotions]

        ## Strengths
        [List 2–3 specific things they did well]

        ## Areas for Improvement
        [List 2–3 specific suggestions for improvement]

        ## Score
        [X]/10

        ## Ideal HR-Expected Answer
        [Return the ideal answer to the interview question as HR expects.
        Write it in a professional candidate style.]

        ## Final Recommendation
        [One-sentence summary and encouragement]
        """

    try:
        result   = llm.invoke(prompt)
        feedback = result.content if hasattr(result, "content") else str(result)

        interview_session.feedback = feedback

        return jsonify({
            "session_id":   interview_session.session_id,
            "feedback":     feedback,
            "session_data": structured_payload,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# NEW ► STOP SESSION  (stops emotion detector)
# ============================================================
@app.route("/stop-session", methods=["POST"])
def stop_session():
    """
    Call this after evaluation or when the user resets.
    """
    if emotion_detector.is_running():
        emotion_detector.stop()
    return jsonify({"success": True, "message": "Session stopped"})


# ============================================================
# Get Session Data  (unchanged)
# ============================================================
@app.route("/session/<session_id>", methods=["GET"])
def get_session(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(sessions[session_id].to_dict())


# ============================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)