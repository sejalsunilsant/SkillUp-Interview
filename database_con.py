from flask import Flask, jsonify
from flask_mysqldb import MySQL
import mysql.connector
from flask_cors import CORS

app = Flask(__name__)
CORS(app) 
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="manager",
        database="interview_tracker"
    )

 
def StoreSession(session_data):
    """
    Stores interview session data in MySQL database
    """

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
        conn.close()
        print("Data Stored")

        return True

    except Exception as e:
        print("DB ERROR:", e)
        return False


def StoreGeneratedQuestion(jd, level, phase, question):
    """
    Stores generated interview question in MySQL database in structured format
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure table exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            job_description TEXT,
            difficulty_level VARCHAR(50),
            question_phase VARCHAR(100),
            question_text TEXT
        )
        """)
        
        # Avoid exact duplicates
        cursor.execute("SELECT id FROM generated_questions WHERE question_text = %s", (question,))
        if not cursor.fetchone():
            query = """
            INSERT INTO generated_questions (job_description, difficulty_level, question_phase, question_text)
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (jd, level, phase, question))
            conn.commit()

        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print("DB ERROR saving question:", e)
        return False


def GetFallbackQuestions(level, phase=None):
    """
    Retrieves questions from DB based on level and optionally phase
    """
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
        conn.close()
        return [r["question_text"] for r in res]
    except Exception as e:
        print("DB ERROR fetching questions:", e)
        return []


@app.route("/test-db")
def test_db(query):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query)  
        data = cursor.fetchall()  
        cursor.close()
        conn.close()
        return f"Connected successfully, data: {data}"
    except Exception as e:
        return str(e)
if __name__=="__main__":
    print(test_db('SELECT * FROM interview_sessions WHERE user_id = 1'))