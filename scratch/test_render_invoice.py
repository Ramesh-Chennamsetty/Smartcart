import os
import sys
from io import BytesIO

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

from utils.pdf_generator import generate_pdf

def test_invoice_render():
    order = {
        'order_id': 12,
        'created_at': '2026-08-10 15:59:24',
        'user_id': 1,
        'payment_status': 'captured',
        'amount': 2500.00
    }
    
    items = [
        {'product_name': 'Test Product 1', 'quantity': 2, 'price': 1000.00},
        {'product_name': 'Test Product 2', 'quantity': 1, 'price': 500.00}
    ]
    
    # We need a Flask app context to use render_template
    from flask import Flask, render_template
    app = Flask(__name__, template_folder=os.path.join(ROOT_DIR, 'templates'))
    
    with app.app_context():
        html = render_template('user/invoice.html', order=order, items=items)
        print("Generated HTML length:", len(html))
        
        pdf_buffer = generate_pdf(html)
        if pdf_buffer is None:
            print("FAILED: generate_pdf returned None!")
        else:
            pdf_bytes = pdf_buffer.getvalue()
            print("SUCCESS: PDF generated, size:", len(pdf_bytes))
            # Save it to a test file
            with open(os.path.join(ROOT_DIR, 'scratch', 'test_invoice.pdf'), 'wb') as f:
                f.write(pdf_bytes)
            print("Saved PDF to scratch/test_invoice.pdf")

if __name__ == "__main__":
    test_invoice_render()
