import os
import sys
import sqlite3
import mysql.connector

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

import config

SQLITE_DB_PATH = os.path.join(ROOT_DIR, "smartcart.db")

def migrate():
    # 1. Connect to MySQL
    print("Connecting to MySQL...")
    try:
        mysql_conn = mysql.connector.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME
        )
    except Exception as e:
        print("Could not connect to MySQL:", e)
        print("We will create empty SQLite tables instead.")
        mysql_conn = None

    # 2. Connect to SQLite
    print(f"Connecting to SQLite ({SQLITE_DB_PATH})...")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_cursor = sqlite_conn.cursor()

    # 3. Create tables in SQLite
    print("Creating tables in SQLite...")
    
    sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS eadmin (
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_image TEXT
    );
    """)
    
    sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS susers (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    );
    """)
    
    sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        category TEXT,
        price REAL,
        image TEXT
    );
    """)
    
    sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_amount REAL,
        user_id INTEGER,
        razorpay_order_id TEXT UNIQUE,
        razorpay_payment_id TEXT UNIQUE,
        amount REAL,
        payment_status TEXT NOT NULL DEFAULT 'legacy',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES susers(user_id)
    );
    """)
    
    sqlite_cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)
    
    sqlite_conn.commit()

    if not mysql_conn:
        print("No MySQL connection. Empty tables ready.")
        sqlite_conn.close()
        return

    # 4. Migrate data table by table
    mysql_cursor = mysql_conn.cursor(dictionary=True)
    tables = ['eadmin', 'susers', 'products', 'orders', 'order_items']
    
    for table in tables:
        print(f"Migrating table {table}...")
        mysql_cursor.execute(f"SELECT * FROM {table}")
        rows = mysql_cursor.fetchall()
        if not rows:
            print(f"No rows in {table} to migrate.")
            continue
            
        columns = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        
        import decimal
        sqlite_data = []
        for row in rows:
            row_data = []
            for col in columns:
                val = row[col]
                if isinstance(val, decimal.Decimal):
                    val = float(val)
                row_data.append(val)
            sqlite_data.append(tuple(row_data))
            
        sqlite_cursor.executemany(sql, sqlite_data)
        sqlite_conn.commit()
        print(f"Migrated {len(rows)} rows for {table}.")

    # Clean up
    mysql_cursor.close()
    mysql_conn.close()
    sqlite_cursor.close()
    sqlite_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
