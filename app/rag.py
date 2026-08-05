import re
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import google.generativeai as genai
from app.config import POLICY_MD_PATH, GEMINI_API_KEY, EMBEDDING_MODEL

class PolicyChunk:
    def __init__(self, section_id: str, title: str, text: str):
        self.section_id = section_id
        self.title = title
        self.text = text
        self.embedding: Optional[List[float]] = None

class PolicyRetrievalEngine:
    """
    RAG (Retrieval-Augmented Generation) Engine.
    Chunks the policy document, computes embeddings using Gemini,
    and performs cosine-similarity matching with a keyword fallback.
    """
    def __init__(self, policy_path: str = str(POLICY_MD_PATH)):
        self.policy_path = policy_path
        self.chunks: List[PolicyChunk] = []
        self._initialize_api()
        self._load_and_chunk_policy()
        self._build_index()

    def _initialize_api(self):
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            self.use_api = True
        else:
            self.use_api = False

    def _load_and_chunk_policy(self):
        """
        Chunking Strategy: Parse the markdown document by policy sections (e.g., Section 1.1, Section 2.1).
        This guarantees semantic boundary alignment, which is superior to arbitrary character count chunking.
        """
        with open(self.policy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Split into main sections
        sections = re.split(r'\n##\s+', content)
        header_text = sections[0]
        self.chunks.append(PolicyChunk(section_id="0", title="General Policy Header", text=header_text.strip()))

        for sec in sections[1:]:
            lines = sec.strip().split('\n')
            if not lines:
                continue
            sec_title = lines[0]
            sec_body = '\n'.join(lines[1:])
            
            # Now split by sub-sections (e.g., **1.1 Dispatch times.**)
            sub_matches = list(re.finditer(r'\*\*([0-9]+\.[0-9]+)\s+([^*]+)\*\*([^*]*)', sec_body))
            
            if not sub_matches:
                self.chunks.append(PolicyChunk(
                    section_id=sec_title.split('.')[0].strip(),
                    title=sec_title,
                    text=f"## {sec_title}\n{sec_body}"
                ))
                continue
                
            for idx, match in enumerate(sub_matches):
                sec_id = match.group(1)
                sub_title = match.group(2).strip()
                start_pos = match.end()
                end_pos = sub_matches[idx+1].start() if idx + 1 < len(sec_body) and idx + 1 < len(sub_matches) else len(sec_body)
                sub_content = sec_body[start_pos:end_pos].strip()
                
                full_chunk_text = f"Section {sec_id} - {sub_title}: {match.group(3)}{sub_content}"
                self.chunks.append(PolicyChunk(
                    section_id=sec_id,
                    title=f"{sec_title} - {sub_title}",
                    text=full_chunk_text
                ))

    def _get_embedding(self, text: str) -> List[float]:
        """
        Fetch embedding from Gemini API. Fallback to basic tf-idf weights if offline/no key.
        """
        if self.use_api:
            try:
                response = genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=text,
                    task_type="retrieval_document"
                )
                return response['embedding']
            except Exception as e:
                # Log embedding failure and use fallback
                print(f"[RAG] Embedding generation failed via API: {e}. Falling back to keyword indices.")
                
        # Simple deterministic fallback embedding: TF-IDF vector hash
        words = re.findall(r'\w+', text.lower())
        
        # Query expansion / Synonym mapping to align user search terms with policy categories
        lower_text = text.lower()
        if any(term in lower_text for term in ["earring", "gold", "ring", "necklace", "jewel", "jewellery", "jewelry"]):
            words.append("jewellery")
        if any(term in lower_text for term in ["socks", "sock", "underwear", "boxer", "briefs", "innerwear"]):
            words.append("innerwear")
            
        vocab = [
            "shipping", "dispatch", "charge", "partial", "delay", "delayed", "lost", "address",
            "return", "window", "hygiene", "final", "sale", "footwear", "box", "refund", "upi",
            "cod", "bank", "card", "exchange", "pickup", "damaged", "wrong", "defective", "socks",
            "innerwear", "jewellery", "jewelry", "earring", "earrings", "gold", "beauty", "fragrance",
            "mask", "gift", "cancel", "cancelled", "fee", "pincode", "delivery", "business", "day"
        ]
        
        # Hardcoded term weights for keyword search relevance (IDF equivalent)
        weights = {
            "return": 1.0, "shipping": 1.0, "exchange": 1.0, "refund": 1.0, "delivery": 1.0, "business": 1.0, "day": 1.0, "window": 1.0,
            "jewellery": 8.0, "jewelry": 8.0, "socks": 8.0, "innerwear": 8.0, "earring": 8.0, "earrings": 8.0, "gold": 8.0, 
            "footwear": 6.0, "box": 6.0, "beauty": 8.0, "fragrance": 8.0, "mask": 8.0, "gift": 8.0,
            "lost": 7.0, "delay": 5.0, "delayed": 5.0, "cancel": 5.0, "cancelled": 5.0, "cod": 7.0, "bank": 7.0, "card": 5.0, "upi": 5.0
        }
        
        vector = [0.0] * len(vocab)
        for w in words:
            for v_idx, vocab_word in enumerate(vocab):
                if vocab_word == w or (len(vocab_word) > 3 and vocab_word in w) or (len(w) > 3 and w in vocab_word):
                    # Add weighted term score
                    vector[v_idx] += weights.get(vocab_word, 1.0)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector

    def _build_index(self):
        """
        Build embeddings index.
        """
        for chunk in self.chunks:
            chunk.embedding = self._get_embedding(chunk.text)

    def retrieve(self, query: str, top_k: int = 2) -> List[Tuple[PolicyChunk, float]]:
        """
        Retrieve relevant policy chunks using Cosine Similarity.
        """
        query_vector = self._get_embedding(query)
        if not query_vector:
            return []

        results = []
        for chunk in self.chunks:
            if chunk.embedding:
                dot_product = np.dot(query_vector, chunk.embedding)
                results.append((chunk, float(dot_product)))
        
        # Sort by similarity score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
