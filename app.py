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
from langchain.chat_models import init_chat_model
from Services.Genrator import InterviewGenratSession


# ── DB helper (unchanged)
from database_con import get_db_connection,StoreSession
import io
import PyPDF2

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.getenv("FLASK_SECRET_KEY", "skillup_secret_key")

# ── LLM ───────────────────────────────────────────────────────────────────────
llm_service=InterviewGenratSession()
llm = ChatGroq(
    groq_api_key=os.getenv("groq_Api"),
    model_name="llama-3.1-8b-instant",
    temperature=0.7,
) #as it  required net connection
# llm = init_chat_model(
#     model="phi-3.1-mini-4k-instruct",
#     model_provider="openai",
#     base_url="http://127.0.0.1:1234/v1",
#     api_key="not-needed"
# )




# ============================================================
# INTERVIEW SESSION MODEL
# ============================================================
class ActiveInterview:
    def __init__(self, jd_text, resume_text, difficulty_level):
        self.session_id       = str(uuid.uuid4())
        self.jd_text          = jd_text
        self.resume_text      = resume_text
        self.difficulty_level = difficulty_level
        self.question_count   = 0
        self.history          = [] 
        self.current_question = None
        self.current_stage    = "Introduction"
        self.timestamp        = datetime.utcnow().isoformat()

active_interviews: dict[str, ActiveInterview] = {}


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

@app.route("/check-login")
def check_login():
    if "user_id" in session:
        return {"logged_in": True}
    else:
        return {"logged_in": False}

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
    return render_template("interview.html", active_page='interview')

@app.route("/dashboard")
@login_required
def dashboard_page():
    return render_template("Dashboard.html", active_page='dashboard')


@app.route("/feedback")
@app.route("/feedback/<session_id>")
@login_required
def feedback_page(session_id=None):
    return render_template("Feedback.html", session_id=session_id, active_page='feedback')


@app.route("/api/feedback/<session_id>")
@login_required
def get_feedback_api(session_id):
    # Try fetching from DB first
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT feedback, question, answer FROM interview_sessions WHERE session_id=%s", (session_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    
    # We also want the history from the memory session if it's still there
    history = []
    if session_id in active_interviews:
        history = active_interviews[session_id].history

    if res and res["feedback"] and res["feedback"] != "Pending Final Evaluation":
        return jsonify({
            "feedback": res["feedback"],
            "last_question": res["question"],
            "last_answer": res["answer"],
            "history": history
        })
    
    # If not in DB but in memory
    if session_id in active_interviews:
        interview = active_interviews[session_id]
        return jsonify({
            "feedback": getattr(interview, 'feedback', "Generating..."),
            "history": interview.history
        })

    return jsonify({"error": "Feedback not found"}), 404


# ============================================================
# NEW ► START SESSION
# ============================================================
@app.route("/start-session", methods=["POST"])
def start_session():
    return jsonify({"success": True, "message": "Session started"})

# Progress dashboard
@app.route("/progress-dashboard",methods=["GET"])
@login_required
def progress_dash():
    user_id=session.get("user_id")
    user_name=session.get("name","user")
    return render_template("Progress.html",user_id=user_id,user_name=user_name, active_page='progress')
# Get user sessions
@app.route("/get-user-sessions",methods=["GET"])
@login_required
def get_user_session():
    user_id=session.get("user_id")
    conn=get_db_connection()
    cursor=conn.cursor(dictionary=True)
    cursor.execute("""
        select session_id, topic, score, feedback, session_date
        from interview_sessions where user_id=%s
        order by session_date desc
    """,(user_id,))
    sessions=cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(sessions)

# ============================================================
# NEW ► RESUME MANAGEMENT
# ============================================================
@app.route("/api/profile/resume", methods=["GET"])
@login_required
def get_user_resume():
    user_id = session.get("user_id")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT resume_text FROM users WHERE user_id=%s", (user_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    resume_text = res["resume_text"] if res and res["resume_text"] else ""
    return jsonify({"resume_text": resume_text})

@app.route("/api/profile/resume", methods=["POST"])
@login_required
def update_user_resume():
    user_id = session.get("user_id")
    resume_text = ""
    
    if request.is_json:
        resume_text = request.json.get("resume_text", "")
    else:
        if 'resume' in request.files:
            file = request.files['resume']
            if file and file.filename.endswith('.pdf'):
                try:
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
                    for page in pdf_reader.pages:
                        resume_text += page.extract_text() + "\n"
                except Exception as e:
                    print("PDF extract error:", e)
            elif file:
                resume_text = file.read().decode('utf-8', errors='ignore')
        else:
            resume_text = request.form.get("resume_text", "")
            
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET resume_text=%s WHERE user_id=%s", (resume_text, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    session["resume_text"] = resume_text
    return jsonify({"success": True, "message": "Resume updated"})

# ============================================================
# STEP 1: Generate HR Question & Create Session
# ============================================================
@app.route("/hr-questions", methods=["POST"])
def hr_questions():
    if request.is_json:
        data = request.json
        level = data.get("level", "medium")
        jd_text = data.get("jd", "")
        session_id = data.get("session_id")
    else:
        # Multipart form data
        level = request.form.get("level", "medium")
        jd_text = request.form.get("jd", "")
        session_id = request.form.get("session_id")

    if jd_text:
        session["jd_text"] = jd_text

    final_jd = jd_text or session.get("jd_text", "")
    
    final_resume = session.get("resume_text", "")
    if session.get("user_id") and not final_resume:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT resume_text FROM users WHERE user_id=%s", (session.get("user_id"),))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        if res and res["resume_text"]:
            final_resume = res["resume_text"]
            session["resume_text"] = final_resume

    try:
        # Check if we have an active session to continue
        if session_id and session_id in active_interviews:
            interview = active_interviews[session_id]
            interview.difficulty_level = level
        else:
            interview = ActiveInterview(final_jd, final_resume, level)
            active_interviews[interview.session_id] = interview
            
        # State machine dict context
        state_dict = {
            "jd_text": interview.jd_text,
            "resume_text": interview.resume_text,
            "question_count": interview.question_count,
            "history": interview.history,
            "level": interview.difficulty_level
        }
        
        question, stage = llm_service.get_next_question(state_dict)
        
        interview.current_question = question
        interview.current_stage = stage
        interview.question_count += 1
        
        # Store the current asked question in history
        current_turn = {"question": question, "answer": "", "feedback": ""}
        interview.history.append(current_turn)
        
        return jsonify({
            "session_id":       interview.session_id,
            "question":         interview.current_question,
            "topic":            interview.current_stage,
            "difficulty_level": interview.difficulty_level,
            "timestamp":        interview.timestamp,
        })
    except Exception as e:
        print("HR QUESTIONS ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ============================================================
# STEP 2-4: Evaluate Response  (now uses EmotionDetector data)
# ============================================================
# ============================================================
# STEP 2-3: Submit Answer without Blocking Evaluation
# ============================================================
@app.route("/submit-answer", methods=["POST"])
def submit_answer():
    data        = request.json
    session_id  = data.get("session_id")
    transcript  = data.get("transcript", "")
    frontend_posture = data.get("posture_data", {})

    if not transcript.strip():
        return jsonify({"error": "Empty transcript"}), 400

    if session_id not in active_interviews:
        return jsonify({"error": "Invalid session ID"}), 400

    interview = active_interviews[session_id]

    # Update the turn in history
    if interview.history:
        interview.history[-1]['answer'] = transcript
        interview.history[-1]['feedback'] = "Pending Evaluation"

    db_topic = f"{interview.current_stage} | {interview.jd_text[:30]}..." if interview.jd_text else interview.current_stage

    db_data = {
        "session_id": interview.session_id,
        "user_id": session.get("user_id"),
        "topic": db_topic,
        "question": interview.current_question,
        "answer": transcript,
        "score": 0,
        "feedback": "Pending Final Evaluation",
        "session_date": datetime.now()
    }

    StoreSession(db_data)

    return jsonify({
        "status": "success",
        "session_id": interview.session_id
    })


# ============================================================
# STEP 4: Evaluate Entire Interview
# ============================================================
@app.route("/finish-interview", methods=["POST"])
def finish_interview():
    data = request.json
    session_id = data.get("session_id")
    
    if session_id not in active_interviews:
        return jsonify({"error": "Invalid session ID"}), 400

    interview = active_interviews[session_id]
    
    try:
        feedback = llm_service.evaluate_all(interview)
        
        # Extract score using regex, expecting '## Score\n[X]/10' or similar
        import re
        score = 0
        match = re.search(r'## Score\s*\n*\s*(\d+(?:\.\d+)?)/10', feedback, re.IGNORECASE)
        if not match:
            # Maybe just simple number match
            match = re.search(r'(\d+)/10', feedback)
        
        if match:
            score = float(match.group(1))
            
        # Update DB with final feedback and score
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE interview_sessions SET feedback=%s, score=%s WHERE session_id=%s", (feedback, score, session_id))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_e:
            print("DB Update Error in finish_interview:", db_e)

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "feedback": feedback
        })
    except Exception as e:
        print("Finish Interview Error:", e)
        return jsonify({"error in app evaluate_all": str(e)}), 500


# ============================================================
# NEW ► STOP SESSION
# ============================================================
@app.route("/stop-session", methods=["POST"])
def stop_session():
    """
    Call this after evaluation or when the user resets.
    """
    return jsonify({"success": True, "message": "Session stopped"})


# ============================================================
# Get Session Data  (unchanged)
# ============================================================
@app.route("/session/<session_id>", methods=["GET"])
def get_session(session_id):
    if session_id not in active_interviews:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
       "session_id": active_interviews[session_id].session_id,
       "question_count": active_interviews[session_id].question_count,
       "current_stage": active_interviews[session_id].current_stage
    })


# ============================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)