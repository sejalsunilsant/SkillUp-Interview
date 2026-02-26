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