"""
RAG Service placeholder (RAG functionality removed).
"""
from typing import List, Dict, Any

class RAGService:
    def __init__(self):
        pass

    def query_questions(self, job_title: str = "", jd_text: str = "", top_k: int = 5) -> List[Dict[str, Any]]:
        return []

    def is_configured(self) -> bool:
        return False
