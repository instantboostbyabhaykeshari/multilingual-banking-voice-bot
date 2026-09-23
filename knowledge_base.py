"""Retrieval over the bundled India business-loan policy PDF.

No facts are invented when the source is missing or a question is outside the
available policy. Every successful lookup carries a page citation.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from pypdf import PdfReader


POLICY_PATH = Path(__file__).parent / "data" / "raw" / "Business_Loan_Policy_Guide.pdf"


class ProductionKnowledgeBase:
    def __init__(self, encoder=None, policy_path: Path = POLICY_PATH):
        if encoder is None:
            from sentence_transformers import SentenceTransformer
            encoder = SentenceTransformer("all-MiniLM-L6-v2")
        self.encoder = encoder
        self.policy_path = Path(policy_path)
        self.structured_db = []
        self.embeddings_matrix = None
        self._build_production_knowledge_base()

    @staticmethod
    def _clean_and_sanitize_text(raw_text: str) -> str:
        text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "[EMAIL REDACTED]", raw_text)
        text = re.sub(r"\+?\d[\d\s-]{9,}\d", "[PHONE REDACTED]", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _build_production_knowledge_base(self):
        if not self.policy_path.is_file():
            raise FileNotFoundError(f"Policy PDF missing: {self.policy_path}")
        reader = PdfReader(str(self.policy_path))
        self.structured_db = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            # Preserve section boundaries and page IDs; arbitrary character
            # slices used to split policy numbers from their explanations.
            sections = re.split(
                r"(?m)^(?=(?:SECTION\s+\d+:|[1-9]\.[1-9]\s+"
                r"[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,}\s*$))",
                page_text,
            )
            for section in sections:
                content = self._clean_and_sanitize_text(section)
                if len(content) < 100:
                    continue
                self.structured_db.append({
                    "record_id": f"policy_p{page_number}_{len(self.structured_db)+1}",
                    "source": self.policy_path.name,
                    "page": page_number,
                    "content": content,
                })
        if not self.structured_db:
            raise ValueError("Policy PDF has no extractable text")
        matrix = np.asarray(self.encoder.encode(
            [r["content"] for r in self.structured_db], convert_to_numpy=True), dtype=float)
        self.embeddings_matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)

    def query(self, user_question: str, market: str = "india") -> dict:
        if market != "india":
            return {"found": False, "reason": f"No verified {market} policy is loaded. Do not quote India policy."}
        if not user_question or not user_question.strip():
            return {"found": False, "reason": "Empty question"}
        vector = np.asarray(self.encoder.encode([user_question], convert_to_numpy=True)[0], dtype=float)
        vector /= np.linalg.norm(vector) + 1e-8
        scores = self.embeddings_matrix @ vector
        best = int(np.argmax(scores))
        if scores[best] < 0.43:
            return {"found": False, "reason": "No sufficiently relevant policy passage found"}
        record = self.structured_db[best]
        result = {"found": True, "score": round(float(scores[best]), 3), **record}
        if "Minimum Loan Amount" in record["content"]:
            result["data_quality_warning"] = (
                "Source conflicts: INR 2,000,000 means 20 lakhs, but the PDF labels it 2 lakhs. "
                "Do not quote the minimum amount without policy-owner clarification."
            )
        return result


if __name__ == "__main__":
    kb = ProductionKnowledgeBase()
    print(kb.query("What is the maximum unsecured business loan amount?"))
