import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="manager",
        database="interview_tracker"
    )

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("DESCRIBE users")
for row in cursor.fetchall():
    print(row)
cursor.execute("DESCRIBE interview_sessions")
for row in cursor.fetchall():
    print(row)
cursor.close()
conn.close()
