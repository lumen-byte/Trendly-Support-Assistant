import pytest
from app.rag import PolicyRetrievalEngine

def test_rag_chunking():
    rag = PolicyRetrievalEngine()
    assert len(rag.chunks) > 0
    
    # Verify we parsed sections correctly
    # Let's search for the lost parcel chunk
    lost_chunks = [c for c in rag.chunks if "1.6" in c.section_id]
    assert len(lost_chunks) == 1
    assert "lost-parcel" in lost_chunks[0].text.lower() or "lost" in lost_chunks[0].text.lower()

def test_rag_retrieval():
    rag = PolicyRetrievalEngine()
    
    # Retrieve query related to lost carrier
    results = rag.retrieve("What happens if my package is lost?")
    assert len(results) > 0
    top_chunk, score = results[0]
    assert "1.6" in top_chunk.section_id or "lost" in top_chunk.text.lower()
    assert score > 0.0

    # Retrieve query related to jewelry returns
    results_jewel = rag.retrieve("Can I return gold earrings?")
    assert len(results_jewel) > 0
    top_chunk_jewel, score_jewel = results_jewel[0]
    assert "2.3" in top_chunk_jewel.section_id or "jewellery" in top_chunk_jewel.text.lower()
