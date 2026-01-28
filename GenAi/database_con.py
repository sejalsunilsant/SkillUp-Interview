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

@app.route("/test-db")
def test_db(query):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        data=cursor.execute(query)
        db_name = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"Connected to database: {db_name[0]}, data:{data}"
    except Exception as e:
        return str(e)
if __name__=="__main__":
    print(test_db('SELECT * FROM interview_sessions WHERE user_id = 1;'))