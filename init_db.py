# init_db.py
import sqlite3
import json
import os

def init_db(db_file=os.environ.get('DATABASE_PATH', 'data/db/roommates.db')):
    os.makedirs(os.path.dirname(db_file), exist_ok=True)
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    
    # Users table with additional profile fields
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        email TEXT,
        profile_image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if columns exist, and if not, add them
    c.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'email' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
        print("Added email column to users table")
    
    if 'profile_image' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN profile_image TEXT")
        print("Added profile_image column to users table")
    
    # FinancingElements table
    c.execute('''
    CREATE TABLE IF NOT EXISTS financing_elements (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        amount REAL NOT NULL,
        type TEXT NOT NULL,  -- "ingreso" or "egreso"
        state TEXT NOT NULL, -- "pending" or "paid"
        month TEXT NOT NULL,
        year INTEGER NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users (id)
    )
    ''')
    
    # Activity logs table
    c.execute('''
    CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        action_type TEXT NOT NULL,  -- "create", "update", "delete"
        entity_type TEXT NOT NULL,  -- "financing_element"
        entity_id TEXT NOT NULL,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create upload folder for profile images if it doesn't exist
    upload_folder = 'static/profile_images'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        print(f"Created profile images directory: {upload_folder}")
    
    # Create config if it doesn't exist
    if not os.path.exists('config.json'):
        default_config = {
            "default_egresos": ["Alquiler", "G. Comunes", "Impuestos", "ANTEL", "UTE", "Seguro"],
            "default_ingresos": ["Aporte Alan", "Aporte Juan", "Aporte Michael", "Renta Cochera"]
        }
        with open('config.json', 'w') as f:
            json.dump(default_config, f)
        print("Created default config.json file")
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == "__main__":
    init_db()