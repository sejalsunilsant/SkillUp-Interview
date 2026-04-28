import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def setup_managed_db():
    print("🚀 Initializing Managed MySQL Database...")
    
    config = {
        "host":     os.getenv("DB_HOST", "localhost"),
        "user":     os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "manager"),
        "database": os.getenv("DB_NAME", "interview_tracker"),
        "port":     int(os.getenv("DB_PORT", 3306))
    }

    # SSL Support
    ssl_ca = os.getenv("DB_SSL_CA")
    ssl_config = {}
    if ssl_ca and os.path.exists(ssl_ca):
        ssl_config = {"ssl_ca": ssl_ca, "ssl_verify_cert": True}

    try:
        # Connect to MySQL
        conn = mysql.connector.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
            port=config["port"],
            **ssl_config
        )
        cursor = conn.cursor()
        
        # Create database
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config['database']}")
        print(f"✅ Database '{config['database']}' ensured.")
        
        cursor.execute(f"USE {config['database']}")

        # 1. Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            role VARCHAR(20) DEFAULT 'user',
            admin_request_status VARCHAR(20) DEFAULT 'none',
            resume_text LONGTEXT,
            streak_count INT DEFAULT 0,
            last_active_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        print("✅ 'users' table ensured.")

        # 2. Interview Sessions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS interview_sessions (
            session_id VARCHAR(100) PRIMARY KEY,
            user_id INT,
            topic VARCHAR(255),
            question TEXT,
            answer LONGTEXT,
            score DECIMAL(3,1),
            feedback LONGTEXT,
            session_date DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """)
        print("✅ 'interview_sessions' table ensured.")

        # 3. Session Metadata (for stateless persistence)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_metadata (
            session_id VARCHAR(100) PRIMARY KEY,
            state_data LONGTEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """)
        print("✅ 'session_metadata' table ensured.")

        # 4. Daily Progress Sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            session_date DATE,
            status VARCHAR(50),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """)
        print("✅ 'sessions' progress table ensured.")

        # 5. Generated Questions Fallback
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            job_description TEXT,
            difficulty_level VARCHAR(50),
            question_phase VARCHAR(100),
            question_text TEXT
        )
        """)
        print("✅ 'generated_questions' table ensured.")

        conn.commit()
        cursor.close()
        conn.close()
        print("\n✨ Managed Database Setup Complete!")

    except Exception as e:
        print(f"❌ Error setting up database: {e}")

if __name__ == "__main__":
    setup_managed_db()
