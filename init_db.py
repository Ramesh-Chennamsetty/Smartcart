import os
import sqlite3
import bcrypt

DB_PATH = os.path.join(os.path.dirname(__file__), "smartcart.db")

def init_db():
    print(f"Initializing database at: {DB_PATH}")
    if os.path.exists(DB_PATH):
        print("Existing database found. Deleting it for a clean setup...")
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create Tables
    print("Creating tables...")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS eadmin (
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        profile_image TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS susers (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        category TEXT,
        price REAL,
        image TEXT
    );
    """)

    cursor.execute("""
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

    cursor.execute("""
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        expiry TEXT NOT NULL,
        role TEXT NOT NULL
    );
    """)

    # Seed admin accounts
    print("Seeding admin accounts...")
    admin_pw_1 = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    admin_pw_2 = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
    cursor.execute(
        "INSERT INTO eadmin (name, email, password, profile_image) VALUES (?, ?, ?, ?)",
        ("Ramesh Chennamsetty", "rameshchennamsetty12@gmail.com", admin_pw_1, "b32bc2792cd0428395aa6ce2055a71e6.jpg")
    )
    cursor.execute(
        "INSERT INTO eadmin (name, email, password, profile_image) VALUES (?, ?, ?, ?)",
        ("ram", "chennamsettyramesh2930@gmail.com", admin_pw_2, None)
    )

    # Seed user accounts
    print("Seeding user accounts...")
    user_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    cursor.execute(
        "INSERT INTO susers (name, email, password) VALUES (?, ?, ?)",
        ("Ramesh Chennamsetty", "rameshchennamsetty12@gmail.com", user_pw)
    )

    # Seed products
    print("Seeding products...")
    products = [
        ('Fresh Apples', 'Crisp and naturally sweet red apples, sold as a 1 kg pack.', 'Groceries', 149.00, 'smartcart-groceries.png'),
        ('Whole Milk', 'Fresh whole milk for breakfast, tea, coffee, and everyday cooking.', 'Dairy', 68.00, 'smartcart-groceries.png'),
        ('Brown Bread', 'Soft whole-wheat bread with a wholesome texture and fresh taste.', 'Bakery', 55.00, 'smartcart-groceries.png'),
        ('Breakfast Cereal', 'Crunchy multigrain cereal for a quick and satisfying breakfast.', 'Breakfast', 225.00, 'smartcart-groceries.png'),
        ('Fresh Carrots', 'Farm-fresh carrots, ideal for salads, curries, and healthy snacks.', 'Vegetables', 48.00, 'smartcart-groceries.png'),
        ('Orange Juice', 'Refreshing orange juice with a bright citrus taste.', 'Beverages', 120.00, 'smartcart-groceries.png')
    ]
    cursor.executemany(
        "INSERT INTO products (name, description, category, price, image) VALUES (?, ?, ?, ?, ?)",
        products
    )

    conn.commit()
    conn.close()
    print("Database initialized and seeded successfully!")

if __name__ == "__main__":
    init_db()
