import chromadb
from chromadb.config import Settings

_client = None
_collection = None

def get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path="./chroma_db", settings=Settings(anonymized_telemetry=False))
        _collection = _client.get_or_create_collection(name="templates")
    return _collection

def add_template_vector(template_id: str, embedding: list[float], metadata: dict = None):
    if metadata is None:
        metadata = {}
    
    get_collection().add(
        ids=[template_id],
        embeddings=[embedding],
        metadatas=[metadata]
    )

def search_templates(query_embedding: list[float], n_results: int = 1, threshold: float = 1.0) -> str | None:
    results = get_collection().query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=['distances', 'metadatas', 'documents']
    )
    if results and results['ids'] and len(results['ids'][0]) > 0:
        distance = results['distances'][0][0]
        if distance <= threshold:
            return results['ids'][0][0]
        else:
            return None
    return None
