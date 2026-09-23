import os
import pypdf
from knowledge_base import ProductionKnowledgeBase

def ingest_loan_pdf():
    pdf_path = os.path.join("data", "raw", "Business_Loan_Policy_Guide.pdf")
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: File not found at path: {pdf_path}")
        return

    print(f"📖 Reading PDF file from: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    extracted_text = ""
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            extracted_text += f"\n--- PAGE {page_num + 1} ---\n" + text

    # Knowledge base instance initialize karke clean & index karein
    kb = ProductionKnowledgeBase()
    
    # Existing dumps ke alawa PDF content bhi add hoga
    cleaned_content = kb._clean_and_sanitize_text(extracted_text)
    
    print("✅ PDF text extracted, cleaned, and PII masked successfully!")
    print(f"Sample Processed Text:\n{cleaned_content[:300]}...\n")

if __name__ == "__main__":
    ingest_loan_pdf()