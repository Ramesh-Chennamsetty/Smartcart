"""Apply the SmartCart order tables migration to the configured database."""

from pathlib import Path
import sys

import mysql.connector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
import config  # noqa: E402


connection = mysql.connector.connect(
    host=config.DB_HOST,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    database=config.DB_NAME,
)
cursor = connection.cursor()

try:
    # Preserve the small legacy Day-12 orders table, if present, while adding
    # the columns and indexes required by the full ordering system.
    cursor.execute("SHOW TABLES LIKE 'orders'")
    if cursor.fetchone():
        cursor.execute("SHOW COLUMNS FROM orders")
        existing_columns = {row[0] for row in cursor.fetchall()}
        if existing_columns == {"order_id", "total_amount"}:
            cursor.execute(
                "ALTER TABLE orders "
                "MODIFY order_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
                "ADD user_id INT NULL, "
                "ADD razorpay_order_id VARCHAR(100) NULL, "
                "ADD razorpay_payment_id VARCHAR(100) NULL, "
                "ADD amount DECIMAL(10,2) NULL, "
                "ADD payment_status VARCHAR(30) NOT NULL DEFAULT 'legacy', "
                "ADD created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "ADD CONSTRAINT uq_orders_razorpay_order UNIQUE (razorpay_order_id), "
                "ADD CONSTRAINT uq_orders_razorpay_payment UNIQUE (razorpay_payment_id), "
                "ADD CONSTRAINT fk_orders_user FOREIGN KEY (user_id) "
                "REFERENCES susers(user_id)"
            )
            cursor.execute(
                "UPDATE orders SET amount = total_amount WHERE amount IS NULL"
            )

    migration = Path(__file__).with_name("create_orders.sql").read_text(
        encoding="utf-8"
    )
    for statement in migration.split(";"):
        if statement.strip():
            cursor.execute(statement)
    connection.commit()
    print("Orders migration applied successfully.")
except mysql.connector.Error:
    connection.rollback()
    for table_name in ("orders", "order_items"):
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        if cursor.fetchone():
            cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
            print(cursor.fetchone()[1])
            cursor.execute(
                f"SELECT COUNT(*) AS row_count FROM `{table_name}`"
            )
            print(f"{table_name} rows: {cursor.fetchone()[0]}")
            if table_name == "orders":
                cursor.execute(
                    "SELECT COUNT(DISTINCT order_id), "
                    "SUM(order_id IS NULL), MIN(order_id), MAX(order_id) FROM orders"
                )
                print(f"orders key statistics: {cursor.fetchone()}")
    raise
finally:
    cursor.close()
    connection.close()
