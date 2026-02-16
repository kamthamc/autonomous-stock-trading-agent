import sqlite3
import os

DB_PATH = "trading_agent.db"

def inspect_db():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(trades)")
        columns = cursor.fetchall()
        print(f"Columns in 'trades' table for {DB_PATH}:")
        for col in columns:
            print(f" - {col[1]} ({col[2]})")

    except Exception as e:
        print(f"❌ Error inspecting DB: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inspect_db()
