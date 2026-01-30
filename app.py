from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_cors import CORS
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from datetime import datetime
import uuid
import bcrypt
from functools import wraps
from database_con import get_db_connection
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

app.secret_key = os.getenv("FLASK_SECRET_KEY", "skillup_secret_key")

llm = ChatGroq(
    groq_api_key=os.getenv("groq_Api"),
    model_name="llama-3.1-8b-instant",   
    temperature=0.7
)

# ============================================================
# STRUCTURED INTERVIEW SESSION SCHEMA
# ============================================================
class InterviewSession:
    """
    Immutable interview session object that stores all context
    """
    def __init__(self, question_text, topic, difficulty_level):
        self.session_id = str(uuid.uuid4())
        self.question_text = question_text
        self.user_transcription = None
        self.topic = topic
        self.difficulty_level = difficulty_level
        self.timestamp = datetime.utcnow().isoformat()
        self.posture_data = None
        self.feedback = None
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "question_text": self.question_text,
            "user_transcription": self.user_transcription,
            "topic": self.topic,
            "difficulty_level": self.difficulty_level,
            "timestamp": self.timestamp,
            "posture_data": self.posture_data,
            "feedback": self.feedback
        }

# In-memory storage (use database in production)
sessions = {}
# ============================================================
# AUTH DECORATOR
# ============================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        if cursor.fetchone():
            return jsonify({
                "success": False,
                "message": "Email already registered"
            })

        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, hashed_pw)
        )
        conn.commit()
        return jsonify({
            "success": True
        })
    except Exception as e:
        print(e)
        return jsonify({
            "success": False,
            "message": "Server error"
        })

    finally:
        cursor.close()
        conn.close()

# ============================================================
# PASSWORD UTILS
# ============================================================
def hash_password(password):
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

def check_password(plain_pw, hashed_pw):
    try:
        return bcrypt.checkpw(
            plain_pw.encode("utf-8"),
            hashed_pw.encode("utf-8")
        )
    except ValueError:
        return False


# ============================================================
# INTERVIEW SESSION MODEL
# ============================================================
class InterviewSession:
    def __init__(self, question_text, topic, difficulty_level):
        self.session_id = str(uuid.uuid4())
        self.question_text = question_text
        self.user_transcription = None
        self.topic = topic
        self.difficulty_level = difficulty_level
        self.timestamp = datetime.utcnow().isoformat()
        self.posture_data = None
        self.feedback = None

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "question_text": self.question_text,
            "user_transcription": self.user_transcription,
            "topic": self.topic,
            "difficulty_level": self.difficulty_level,
            "timestamp": self.timestamp,
            "posture_data": self.posture_data,
            "feedback": self.feedback
        }

# In-memory storage (DB in production)
sessions_store = {}

# ============================================================
# AUTH ROUTES
# ============================================================
@app.route("/", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def api_login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT user_id, name, email, password
        FROM users
        WHERE email = %s
    """, (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and check_password(password, user["password"]):
        session["user_id"] = user["user_id"]
        session["name"] = user["name"]

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
# STEP 1: Generate HR Question & Create Session
# ============================================================
@app.route("/hr-questions", methods=["POST"])
def hr_questions():
    """
    Generate interview question and create immutable session object
    """
    data = request.json
    level = data.get("level", "easy")
    count = data.get("count", 1)
    topic = data.get("topic", "Technical")

    prompt = f"""
    You are an experienced HR interviewer conducting a {level}-level interview.
    
    Generate {count} {level}-level interview question related to: {topic}
    
    The question should assess:
    -related to topic based on prctical application
    Return ONLY the question text, nothing else.
    """

    try:
        result = llm.invoke(prompt)
        question = result.content if hasattr(result, "content") else str(result)
        
        # Create immutable session object
        session = InterviewSession(
            question_text=question.strip(),
            topic=topic,
            difficulty_level=level
        )
        
        # Store session
        sessions[session.session_id] = session
        
        return jsonify({
            "session_id": session.session_id,
            "question": session.question_text,
            "topic": session.topic,
            "difficulty_level": session.difficulty_level,
            "timestamp": session.timestamp
        })
    
    except Exception as e:
        print("HR QUESTIONS ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ============================================================
# STEP 2-4: Evaluate Response with Structured Payload
# ============================================================
@app.route("/evaluate", methods=["POST"])
def evaluate():
    """
    Context-aware evaluation using complete session object
    """
    data = request.json
    session_id = data.get("session_id")
    transcript = data.get("transcript", "")
    posture_data = data.get("posture_data", {})
    
    if not transcript.strip():
        return jsonify({"error": "Empty transcript"}), 400

    # Retrieve session
    if session_id not in sessions:
        return jsonify({"error": "Invalid session ID"}), 400
    
    session = sessions[session_id]
    
    # Update session with user response (maintain immutability concept)
    session.user_transcription = transcript
    session.posture_data = posture_data
    
    # Create structured payload for LLM
    structured_payload = {
        "session_id": session.session_id,
        "question_text": session.question_text,
        "user_transcription": session.user_transcription,
        "topic": session.topic,
        "difficulty_level": session.difficulty_level,
        "timestamp": session.timestamp,
        "posture_data": {
            "duration": posture_data.get('duration', 0),
            "stability": posture_data.get('stability', 'Unknown'),
            "notes": posture_data.get('notes', 'Not available')
        }
    }

    # Build comprehensive evaluation prompt
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

        POSTURE & BODY LANGUAGE DATA:
        - Duration: {structured_payload['posture_data']['duration']} seconds
        - Stability: {structured_payload['posture_data']['stability']}
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

        ## Body Language & Posture
        - Stability: [Comment on their physical presence]
        - Engagement: [Based on duration and consistency]

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
        result = llm.invoke(prompt)
        feedback = result.content if hasattr(result, "content") else str(result)
        
        # Store feedback in session
        session.feedback = feedback
        
        return jsonify({
            "session_id": session.session_id,
            "feedback": feedback,
            "session_data": structured_payload
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# Get Session Data
# ============================================================
@app.route("/session/<session_id>", methods=["GET"])
def get_session(session_id):
    """
    Retrieve complete session data
    """
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify(sessions[session_id].to_dict())


if __name__ == "__main__":
    app.run(debug=True, port=5000)