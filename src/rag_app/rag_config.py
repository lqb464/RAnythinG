"""RAG pipeline model and retrieval configuration."""

# Embedding: multilingual dense retrieval
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
# Prefix required by E5 models ("query: " / "passage: "); set to "" for BGE/other models
EMBEDDING_QUERY_PREFIX = "query: "
EMBEDDING_PASSAGE_PREFIX = "passage: "

# Cross-encoder reranker (multilingual)
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

# Instruction-tuned causal LM for synthesis (Vietnamese + English)
GENERATION_MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"

# Chunking tuned for E5-small (keep chunks self-contained)
CHUNK_MAX_WORDS = 180
CHUNK_MIN_WORDS = 20
SEMANTIC_BREAK_PERCENTILE = 25

# Retrieval pipeline
RETRIEVAL_CANDIDATES = 32
RERANK_POOL_SIZE = 16
RERANK_TOP_K = 6
FINAL_TOP_K = 4
RRF_K = 60
MAX_QUERY_VARIANTS = 3

# Generation
MAX_NEW_TOKENS = 512
GENERATION_TEMPERATURE = 0.3

# Graph RAG — set ENABLE_GRAPH_RAG=False to skip KG building during indexing
ENABLE_GRAPH_RAG = False
GRAPH_MAX_EXPANDED = 24
GRAPH_MIN_SHARED_TERMS = 2
GRAPH_GLOBAL_TOP_COMMUNITIES = 3

# Document parsing (set RAG_USE_DOCLING=0 to disable Docling)
USE_DOCLING_DEFAULT = True
