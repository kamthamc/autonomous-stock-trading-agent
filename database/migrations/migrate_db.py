import sqlite3
import os

DB_PATH = "trading_agent.db"

def run_migrations():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check and alter trades table
        cursor.execute("PRAGMA table_info(trades)")
        columns = [info[1] for info in cursor.fetchall()]
        
        new_columns = {
            "is_manual": "BOOLEAN DEFAULT 0",
            "order_type": "VARCHAR DEFAULT 'MARKET'",
            "limit_price": "FLOAT",
            "stop_price": "FLOAT",
            "asset_type": "VARCHAR DEFAULT 'STOCK'",
            "option_strike": "FLOAT",
            "option_expiry": "VARCHAR"
        }
        
        for col, col_type in new_columns.items():
            if col not in columns:
                print(f"Adding '{col}' column to 'trades' table...")
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                conn.commit()
                print(f"✅ Successfully added '{col}'.")
            else:
                print(f"ℹ️ Column '{col}' already exists in 'trades'.")
                
        # Create account_equity_snapshots table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                region VARCHAR NOT NULL,
                cash FLOAT NOT NULL,
                holdings_value FLOAT NOT NULL,
                total_equity FLOAT NOT NULL
            )
        ''')
        print("✅ Ensured 'account_equity_snapshots' table exists.")
        
        # Create watched_tickers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watched_tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                added_at DATETIME NOT NULL,
                symbol VARCHAR NOT NULL,
                region VARCHAR NOT NULL,
                source_trend VARCHAR,
                notes VARCHAR
            )
        ''')
        print("✅ Ensured 'watched_tickers' table exists.")
        
        conn.commit()
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migrations()
