import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

db_config = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "manager"),
    "database": os.getenv("DB_NAME", "interview_tracker")
}

def promote_to_admin(email):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET role = 'admin' WHERE email = %s", (email,))
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"User {email} promoted to admin.")
        else:
            print(f"User {email} not found.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Failed to promote user: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        promote_to_admin(sys.argv[1])
    else:
        print("Please provide an email address.")
