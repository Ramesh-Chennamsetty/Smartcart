import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

from app import app, get_db_connection

def test_download():
    # Make sure we have user_id = 1 and order_id = 12 in the database,
    # or just look up what orders exist for user_id = 1.
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE user_id = 1 LIMIT 1")
    order = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not order:
        print("No order found in db for user_id = 1. Can't run route test.")
        return
        
    order_id = order['order_id']
    print(f"Testing download_invoice for order_id: {order_id}")
    
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['user_name'] = 'Ramesh Chennamsetty'
        
    response = client.get(f'/user/download-invoice/{order_id}')
    print("Status Code:", response.status_code)
    print("Headers:")
    for header, value in response.headers.items():
        print(f"  {header}: {value}")
    
    if response.status_code == 200:
        print("Success! Response size:", len(response.data))
    else:
        print("Failure! Response data sample:")
        print(response.data[:500])

if __name__ == "__main__":
    test_download()
