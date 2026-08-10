import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT_DIR)

from utils.pdf_generator import generate_pdf


class InvoicePdfGenerationTest(unittest.TestCase):
    def test_generate_pdf_returns_non_empty_bytes(self):
        html = "<html><body><h1>Invoice</h1><p>Hello SmartCart</p></body></html>"
        pdf_buffer = generate_pdf(html)

        self.assertIsNotNone(pdf_buffer)
        self.assertGreater(len(pdf_buffer.getvalue()), 0)


if __name__ == "__main__":
    unittest.main()
