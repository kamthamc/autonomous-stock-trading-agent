import sqlite3
import os

DB_PATH = "trading_agent.db"

def migrate_trades_table():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(trades)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "region" not in columns:
            print("Adding 'region' column to 'trades' table...")
            cursor.execute("ALTER TABLE trades ADD COLUMN region VARCHAR")
            conn.commit()
            print("✅ Successfully added 'region' column.")
        else:
            print("ℹ️ Column 'region' already exists in 'trades' table.")
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_trades_table()
