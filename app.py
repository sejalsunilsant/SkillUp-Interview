import os
from flask import Flask, request, jsonify, session, redirect, url_for, render_template
from flask_cors import CORS
from flask_compress import Compress
from dotenv import load_dotenv
from datetime import datetime
import uuid
import bcrypt
from functools import wraps
from Services.Genrator import InterviewGenratSession


# ── DB helper (unchanged)
from database_con import get_db_connection, StoreSession, CheckDailyLimit, CreateSessionRecord, UpdateStreak, GetUserStreakInfo
import io
import PyPDF2

import logging

# ── LOGGING ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__)
Compress(app)

# ── SECURITY SETTINGS ──────────────────────────────────────────────────────
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800, # 30 mins
    SEND_FILE_MAX_AGE_DEFAULT=31536000 # 1 year cache for static assets
)
CORS(app, resources={r"/*": {"origins": "*"}})
app.secret_key = os.getenv("FLASK_SECRET_KEY", "prod_fallback_secret_7832")

if not os.getenv("groq_Api"):
    logger.warning("GROQ_API key is not set. Questions will fail to generate.")

# ── LLM ───────────────────────────────────────────────────────────────────────
llm_service=InterviewGenratSession()


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

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "jd_text": self.jd_text,
            "resume_text": self.resume_text,
            "difficulty_level": self.difficulty_level,
            "question_count": self.question_count,
            "history": self.history,
            "current_question": self.current_question,
            "current_stage": self.current_stage,
            "timestamp": self.timestamp
        }

    @staticmethod
    def from_dict(d):
        obj = ActiveInterview(d["jd_text"], d["resume_text"], d["difficulty_level"])
        obj.session_id = d["session_id"]
        obj.question_count = d["question_count"]
        obj.history = d["history"]
        obj.current_question = d["current_question"]
        obj.current_stage = d["current_stage"]
        obj.timestamp = d["timestamp"]
        return obj

from database_con import SaveInterviewState, LoadInterviewState
import json

def get_active_interview(session_id):
    """Refactored to check memory first, then DB for stateless scalability"""
    if session_id in active_interviews:
        return active_interviews[session_id]
    
    state_json = LoadInterviewState(session_id)
    if state_json:
        try:
            data = json.loads(state_json)
            obj = ActiveInterview.from_dict(data)
            active_interviews[session_id] = obj # Cache in memory for this worker
            return obj
        except Exception as e:
            logger.error(f"Failed to deserialize session {session_id}: {e}")
    return None

def persist_interview(interview):
    """Saves to memory and DB"""
    active_interviews[interview.session_id] = interview
    SaveInterviewState(interview.session_id, json.dumps(interview.to_dict()))

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

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return jsonify({"success": False, "message": "Admin access required"}), 403
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
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():
    data     = request.get_json()
    name     = data.get("name")
    email    = data.get("email")
    request_admin = data.get("request_admin", False)
    admin_status = 'pending' if request_admin else 'none'

    conn   = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "message": "Email already registered"})

        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (name, email, password, admin_request_status) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_pw, admin_status),
        )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Registration error for {email}: {e}")
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
        "SELECT user_id, name, email, password, role FROM users WHERE email = %s", (email,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password(password, user["password"]):
        session["user_id"] = user["user_id"]
        session["name"]    = user["name"]
        session["role"]    = user["role"]
        return jsonify({"message": "Login successful", "role": user["role"]}), 200

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
    return render_template("dashboard.html", active_page='dashboard')

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard_page():
    return render_template("admin_dashboard.html", active_page='admin')


@app.route("/feedback")
@app.route("/feedback/<session_id>")
@login_required
def feedback_page(session_id=None):
    return render_template("feedback.html", session_id=session_id, active_page='feedback')


@app.route("/api/feedback/<session_id>")
@login_required
def get_feedback_api(session_id):
    user_id = session.get("user_id")
    # Try fetching from DB first
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT feedback, question, answer, user_id FROM interview_sessions WHERE session_id=%s", (session_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    
    # Security check: Does this record belong to the current user?
    if res and res["user_id"] != user_id:
        return jsonify({"error": "Unauthorized access to this session's feedback"}), 403

    # We also want the history from the memory session if it's still there
    history = []
    interview = get_active_interview(session_id)
    if interview:
        history = interview.history

    if res and res["feedback"] and res["feedback"] != "Pending Final Evaluation":
        return jsonify({
            "feedback": res["feedback"],
            "last_question": res["question"],
            "last_answer": res["answer"],
            "history": history
        })
    
    # If not in DB but in memory/metadata
    interview = get_active_interview(session_id)
    if interview:
        return jsonify({
            "feedback": getattr(interview, 'feedback', "Generating..."),
            "history": interview.history
        })

    return jsonify({"error": "Feedback not found"}), 404


# ============================================================
# NEW ► START SESSION
# ============================================================
@app.route("/start-session", methods=["POST"])
@login_required
def start_session():
    user_id = session.get("user_id")
    
    # Check if user already completed an interview today
    if CheckDailyLimit(user_id):
        return jsonify({
            "success": False, 
            "message": "You’ve already completed today’s interview. Come back tomorrow."
        }), 403
        
    # Create or update session record to 'Started'
    CreateSessionRecord(user_id, 'Started')
    
    return jsonify({"success": True, "message": "Session started"})

@app.route("/user-profile", methods=["GET"])
@login_required
def user_profile():
    user_id = session.get("user_id")
    streak_info = GetUserStreakInfo(user_id)
    return jsonify({
        "success": True,
        "name": session.get("name"),
        "streak_info": streak_info
    })

# Chrome DevTools occasionally pokes this path; silence the 404 log
@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools_json():
    return jsonify({}), 200

# Progress dashboard
@app.route("/progress-dashboard",methods=["GET"])
@login_required
def progress_dash():
    user_id=session.get("user_id")
    user_name=session.get("name","user")
    return render_template("progress.html",user_id=user_id,user_name=user_name, active_page='progress')
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
    
    # Format the data properly to avoid JSON serialization errors
    for session_record in sessions:
        if isinstance(session_record.get('session_date'), datetime):
            session_record['session_date'] = session_record['session_date'].strftime('%Y-%m-%d %H:%M:%S')
        elif session_record.get('session_date'):
            session_record['session_date'] = str(session_record['session_date'])
            
        if session_record.get('score') is not None:
            session_record['score'] = float(session_record['score'])
            
    cursor.close()
    conn.close()
    return jsonify(sessions)

# ============================================================
# HR CHATBOT ENDPOINT
# ============================================================
@app.route("/api/hr-chat", methods=["POST"])
@login_required
def hr_chat():
    data = request.json
    user_message = data.get("message", "")
    chat_history = data.get("history", []) # List of {role: 'user'|'assistant', content: '...'}
    
    if not user_message:
        return jsonify({"error": "Message is required"}), 400
        
    user_id = session.get("user_id")
    user_name = session.get("name", "User")
    
    # 1. Get Progress Data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT topic, score, feedback, session_date
        FROM interview_sessions WHERE user_id=%s
        ORDER BY session_date DESC LIMIT 5
    """, (user_id,))
    progress_data = cursor.fetchall()
    
    # 2. Get Resume
    cursor.execute("SELECT resume_text FROM users WHERE user_id=%s", (user_id,))
    res = cursor.fetchone()
    resume_text = res["resume_text"] if res and res["resume_text"] else ""
    
    cursor.close()
    conn.close()
    
    # 3. Call LLM
    response = llm_service.chat_with_hr(user_name, progress_data, resume_text, user_message, chat_history)
    
    return jsonify({"response": response})

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
                    logger.error(f"PDF extract error for user {user_id}: {e}")
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
@login_required
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
        interview = get_active_interview(session_id) if session_id else None
        
        if interview:
            interview.difficulty_level = level
        else:
            interview = ActiveInterview(final_jd, final_resume, level)
            persist_interview(interview)
            
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
        
        # Guarantee it shows up immediately on the progress dashboard! 
        if session.get("user_id"):
            topic_str = f"{stage} | {interview.jd_text[:20]}..." if interview.jd_text else stage
            db_data = {
                "session_id": interview.session_id,
                "user_id": session.get("user_id"),
                "topic": topic_str,
                "question": question,
                "answer": "In Progress / Unanswered",
                "score": 0,
                "feedback": "In Progress...",
                "session_date": datetime.now()
            }
            StoreSession(db_data)
        
        persist_interview(interview)
        
        return jsonify({
            "session_id":       interview.session_id,
            "question":         interview.current_question,
            "topic":            interview.current_stage,
            "difficulty_level": interview.difficulty_level,
            "timestamp":        interview.timestamp,
        })
    except Exception as e:
        logger.error(f"HR QUESTIONS ERROR: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================
# STEP 2-4: Evaluate Response  (now uses EmotionDetector data)
# ============================================================
# ============================================================
# STEP 2-3: Submit Answer without Blocking Evaluation
# ============================================================
@app.route("/submit-answer", methods=["POST"])
@login_required
def submit_answer():
    data        = request.json
    session_id  = data.get("session_id")
    transcript  = data.get("transcript", "")
    frontend_posture = data.get("posture_data", {})

    if not transcript.strip():
        return jsonify({"error": "Empty transcript"}), 400

    interview = get_active_interview(session_id)
    if not interview:
        return jsonify({"error": "Invalid or expired session ID"}), 400

    # Update the turn in history with transcript and posture data
    if interview.history:
        interview.history[-1]['answer'] = transcript
        interview.history[-1]['feedback'] = "Pending Evaluation"
        interview.history[-1]['posture'] = frontend_posture

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
    persist_interview(interview)

    return jsonify({
        "status": "success",
        "session_id": interview.session_id
    })


# ============================================================
# STEP 4: Evaluate Entire Interview
# ============================================================
@app.route("/finish-interview", methods=["POST"])
@login_required
def finish_interview():
    data = request.json
    session_id = data.get("session_id")
    
    interview = get_active_interview(session_id)
    if not interview:
        return jsonify({"error": "Invalid or expired session ID"}), 400
    
    try:
        feedback = llm_service.evaluate_all(interview)
        
        # Extract score using resilient regex avoiding format failures
        import re
        score = 0
        match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', feedback)
        
        if match:
            score = float(match.group(1))
            
        # Safely Upsert: Guarantee row exists, and force overwrite score/feedback.
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            topic_str = interview.current_stage if interview.current_stage else "Final Interview Review"
            question_str = interview.current_question if interview.current_question else "Overall assessment"
            cursor.execute("""
                INSERT INTO interview_sessions 
                (session_id, user_id, topic, question, answer, score, feedback, session_date)
                VALUES (%s, %s, %s, %s, 'Auto-Completed / Skipped', %s, %s, NOW())
                ON DUPLICATE KEY UPDATE 
                feedback = VALUES(feedback),
                score = VALUES(score)
            """, (session_id, session.get("user_id"), topic_str, question_str, score, feedback))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as db_e:
            logger.error(f"DB Update Error in finish_interview for session {session_id}: {db_e}")

        # Update streak and mark session as completed
        user_id = session.get("user_id")
        if user_id:
            UpdateStreak(user_id)

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "feedback": feedback
        })
    except Exception as e:
        logger.error(f"Finish Interview Error for session {session_id}: {e}", exc_info=True)
        return jsonify({"error in app evaluate_all": str(e)}), 500


# ============================================================
# NEW ► STOP SESSION
# ============================================================
@app.route("/stop-session", methods=["POST"])
@login_required
def stop_session():
    """
    Call this after evaluation or when the user resets.
    """
    return jsonify({"success": True, "message": "Session stopped"})


# ============================================================
# Get Session Data  (unchanged)
# ============================================================
@app.route("/session/<session_id>", methods=["GET"])
@login_required
def get_session(session_id):
    interview = get_active_interview(session_id)
    if not interview:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({
       "session_id": interview.session_id,
       "question_count": interview.question_count,
       "current_stage": interview.current_stage
    })


# ============================================================
# ADMIN API ROUTES
# ============================================================
@app.route("/api/admin/stats", methods=["GET"])
@admin_required
def admin_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Total Users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']
    
    # Total Interview Sessions
    cursor.execute("SELECT COUNT(*) as count FROM interview_sessions")
    total_sessions = cursor.fetchone()['count']
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "success": True,
        "total_users": total_users,
        "total_sessions": total_sessions
    })

@app.route("/api/admin/requests", methods=["GET"])
@admin_required
def admin_requests():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch pending admin requests
    cursor.execute("""
        SELECT user_id, name, email, admin_request_status 
        FROM users 
        WHERE admin_request_status = 'pending'
    """)
    requests = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify(requests)

@app.route("/api/admin/handle-request", methods=["POST"])
@admin_required
def handle_admin_request():
    data = request.json
    target_user_id = data.get("user_id")
    action = data.get("action") # 'approve' or 'reject'
    
    if not target_user_id or action not in ['approve', 'reject']:
        return jsonify({"success": False, "message": "Invalid data"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if action == 'approve':
        cursor.execute("""
            UPDATE users 
            SET role = 'admin', admin_request_status = 'approved' 
            WHERE user_id = %s
        """, (target_user_id,))
    else:
        cursor.execute("""
            UPDATE users 
            SET admin_request_status = 'rejected' 
            WHERE user_id = %s
        """, (target_user_id,))
        
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True, "message": f"User {action}d successfully"})

@app.route("/api/user/request-admin", methods=["POST"])
@login_required
def request_admin_access():
    user_id = session.get("user_id")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE users 
        SET admin_request_status = 'pending' 
        WHERE user_id = %s AND role != 'admin'
    """, (user_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"success": True, "message": "Admin request sent"})

# ============================================================
if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=5000)