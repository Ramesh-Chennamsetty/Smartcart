from io import BytesIO

from xhtml2pdf import pisa


def generate_pdf(template_html: str):
    """Convert invoice HTML into PDF bytes in memory."""
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(template_html, dest=pdf_buffer)

    if pisa_status.err:
        return None

    return pdf_buffer
