import mysql.connector
from mysql.connector import pooling
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── DB POLLING CONFIG ──────────────────────────────────────────────────────
# Using a connection pool is more efficient for production workloads
db_password = os.getenv("DB_PASSWORD")
if not db_password and os.getenv("FLASK_ENV") == "production":
    raise RuntimeError("DB_PASSWORD must be set in production")

db_config = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": db_password or "manager",
    "database": os.getenv("DB_NAME", "interview_tracker"),
    "port":     int(os.getenv("DB_PORT") or 3306)
}

# ── SSL CONFIG (REQUIRED FOR AIVEN) ────────────────────────────────────────
ssl_ca = os.getenv("DB_SSL_CA")
if ssl_ca and os.path.exists(ssl_ca):
    db_config["ssl_ca"] = ssl_ca
    db_config["ssl_verify_cert"] = True
    logger.info(f"SSL CA certificate enabled: {ssl_ca}")

try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="skillup_pool",
        pool_size=5,
        pool_reset_session=True,
        **db_config
    )
    logger.info("Database connection pool initialized")
except Exception as e:
    logger.error(f"Failed to initialize DB connection pool: {e}")
    connection_pool = None

def get_db_connection():
    if connection_pool:
        return connection_pool.get_connection()
    return mysql.connector.connect(**db_config)

def StoreSession(session_data):
    """Stores interview session data in MySQL database"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
        INSERT INTO interview_sessions
        (session_id, user_id, topic, question, answer, score, feedback, session_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        topic = VALUES(topic),
        question = VALUES(question),
        answer = VALUES(answer),
        session_date = VALUES(session_date)
        """
        values = (
            session_data["session_id"],
            session_data["user_id"],
            session_data["topic"],
            session_data["question"],
            session_data["answer"],
            session_data["score"],
            session_data["feedback"],
            session_data["session_date"]
        )
        cursor.execute(query, values)
        conn.commit()
        cursor.close()
        logger.info(f"Session {session_data['session_id']} stored successfully")
        return True
    except Exception as e:
        logger.error(f"DB Error StoreSession: {e}")
        return False
    finally:
        if conn: conn.close()

def StoreGeneratedQuestion(jd, level, phase, question):
    """Stores generated interview question in structured format"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            job_description TEXT,
            difficulty_level VARCHAR(50),
            question_phase VARCHAR(100),
            question_text TEXT
        )
        """)
        cursor.execute("SELECT id FROM generated_questions WHERE question_text = %s", (question,))
        if not cursor.fetchone():
            query = "INSERT INTO generated_questions (job_description, difficulty_level, question_phase, question_text) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (jd, level, phase, question))
            conn.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"DB Error StoreGeneratedQuestion: {e}")
        return False
    finally:
        if conn: conn.close()

def GetFallbackQuestions(level, phase=None):
    """Retrieves questions from DB based on level and optionally phase"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if phase:
            query = "SELECT question_text FROM generated_questions WHERE difficulty_level=%s AND question_phase=%s ORDER BY id DESC LIMIT 50"
            cursor.execute(query, (level, phase))
        else:
            query = "SELECT question_text FROM generated_questions WHERE difficulty_level=%s ORDER BY id DESC LIMIT 50"
            cursor.execute(query, (level,))
        res = cursor.fetchall()
        cursor.close()
        return [r["question_text"] for r in res]
    except Exception as e:
        logger.error(f"DB Error GetFallbackQuestions: {e}")
        return []
    finally:
        if conn: conn.close()

def CheckDailyLimit(user_id):
    """Checks if the user has already completed an interview today"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT id FROM sessions WHERE user_id = %s AND session_date = CURDATE() AND status = 'Completed'"
        cursor.execute(query, (user_id,))
        res = cursor.fetchone()
        cursor.close()
        return res is not None
    except Exception as e:
        logger.error(f"Error CheckDailyLimit: {e}")
        return False
    finally:
        if conn: conn.close()

def CreateSessionRecord(user_id, status='Started'):
    """Creates a new entry in the sessions table for tracking daily attempts"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sessions WHERE user_id = %s AND session_date = CURDATE()", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("UPDATE sessions SET status = %s WHERE id = %s", (status, existing[0]))
        else:
            query = "INSERT INTO sessions (user_id, session_date, status) VALUES (%s, CURDATE(), %s)"
            cursor.execute(query, (user_id, status))
            
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error CreateSessionRecord: {e}")
        return False
    finally:
        if conn: conn.close()

def UpdateStreak(user_id):
    """Updates the user's streak based on consecutive daily activity"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        from datetime import datetime, timedelta
        
        cursor.execute("SELECT streak_count, last_active_date FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user: return False
        
        streak = user.get('streak_count') or 0
        last_date = user.get('last_active_date')
        today = datetime.now().date()
        
        if last_date == today:
            cursor.execute("UPDATE sessions SET status = 'Completed' WHERE user_id = %s AND session_date = %s", 
                           (user_id, today))
            conn.commit()
            return True
            
        yesterday = today - timedelta(days=1)
        
        if last_date == yesterday:
            streak += 1
        else:
            streak = 1
            
        cursor.execute("UPDATE users SET streak_count = %s, last_active_date = %s WHERE user_id = %s", 
                       (streak, today, user_id))
        
        cursor.execute("UPDATE sessions SET status = 'Completed' WHERE user_id = %s AND session_date = %s", 
                       (user_id, today))
        
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error UpdateStreak: {e}")
        return False
    finally:
        if conn: conn.close()

def GetUserStreakInfo(user_id):
    """Retrieves streak and today's status for the user profile"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT streak_count, last_active_date FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        cursor.execute("SELECT status FROM sessions WHERE user_id = %s AND session_date = CURDATE()", (user_id,))
        session_today = cursor.fetchone()
        
        cursor.close()
        
        streak = user['streak_count'] if user and user['streak_count'] else 0
        status = session_today['status'] if session_today else 'Available'
        
        # Calculate hours until tomorrow
        from datetime import datetime, time, timedelta
        now = datetime.now()
        tomorrow_midnight = datetime.combine(now.date() + timedelta(days=1), time.min)
        delta = tomorrow_midnight - now
        hours_until = int(delta.total_seconds() // 3600)
        
        return {
            "streak_count": streak,
            "last_active_date": str(user['last_active_date']) if user and user['last_active_date'] else None,
            "today_status": status,
            "hours_until_next": hours_until
        }
    except Exception as e:
        logger.error(f"Error GetUserStreakInfo: {e}")
        return {"streak_count": 0, "last_active_date": None, "today_status": "Error", "hours_until_next": 0}
    finally:
        if conn: conn.close()

def SaveInterviewState(session_id, state_json):
    """Saves the entire ActiveInterview object state as JSON for stateless worker support"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_metadata (
                session_id VARCHAR(100) PRIMARY KEY,
                state_data LONGTEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO session_metadata (session_id, state_data) 
            VALUES (%s, %s) 
            ON DUPLICATE KEY UPDATE state_data = VALUES(state_data)
        """, (session_id, state_json))
        conn.commit()
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"Error SaveInterviewState: {e}")
        return False
    finally:
        if conn: conn.close()

def LoadInterviewState(session_id):
    """Loads the ActiveInterview object state from the database"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT state_data FROM session_metadata WHERE session_id = %s", (session_id,))
        res = cursor.fetchone()
        cursor.close()
        return res['state_data'] if res else None
    except Exception as e:
        logger.error(f"Error LoadInterviewState: {e}")
        return None
    finally:
        if conn: conn.close()