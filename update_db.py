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

def update_db():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Add role column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'")
            print("Added 'role' column to 'users' table.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Duplicate column name
                print("'role' column already exists.")
            else:
                print(f"Error adding 'role' column: {err}")

        # Add admin_request_status column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN admin_request_status VARCHAR(20) DEFAULT 'none'")
            print("Added 'admin_request_status' column to 'users' table.")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Duplicate column name
                print("'admin_request_status' column already exists.")
            else:
                print(f"Error adding 'admin_request_status' column: {err}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database update completed.")
    except Exception as e:
        print(f"Failed to update database: {e}")

if __name__ == "__main__":
    update_db()
