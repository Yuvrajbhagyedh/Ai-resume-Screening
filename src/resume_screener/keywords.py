"""Keyword/phrase vocabularies used by eligibility and scoring.

Kept as plain data (not logic) so the bar for "genuine" evidence is easy to
inspect, tune, and unit-test without touching pipeline code.
"""

from __future__ import annotations

# --- Python evidence -------------------------------------------------------
# The literal word "python" counts as genuine evidence wherever it appears
# (skills list, project bullet, work experience, implementation-language
# note) -- the assignment explicitly allows a plain skill mention.
PYTHON_FRAMEWORKS = {
    "django", "flask", "fastapi", "numpy", "pandas", "pytorch", "tensorflow",
    "scikit-learn", "sklearn", "keras", "sqlalchemy", "celery", "pytest",
    "streamlit", "matplotlib", "seaborn", "scipy", "pydantic", "uvicorn",
    "gunicorn", "pyspark", "beautifulsoup", "scrapy", "airflow", "opencv-python",
    "gradio", "poetry", "conda",
}

# --- AI / LLM / RAG / agentic evidence --------------------------------------
# Specific enough that a hit is inherently meaningful -- no extra context
# needed. Bare "AI" / "machine learning" are deliberately excluded: the
# assignment asks us not to treat those generic words as sufficient.
# Named frameworks/libraries live here unconditionally: actually knowing and
# using a specific agentic framework (LangChain, LangGraph, LlamaIndex,
# Google ADK, ...) is itself meaningful, even as a bare skill-list mention --
# unlike a generic hosted-provider API name (see AI_PROVIDER_API_TERMS below).
AI_STRONG_TERMS = {
    "llm", "large language model", "large language models",
    "retrieval augmented generation", "retrieval-augmented generation",
    "langchain", "langgraph", "llamaindex", "llama index", "google adk",
    "autogen", "crewai", "crew ai",
    "semantic kernel", "vector database", "vector store", "vector db",
    "pinecone", "chromadb", "chroma db", "faiss", "weaviate", "qdrant",
    "embedding model", "text embeddings", "prompt engineering",
    "fine-tuning", "fine tuned", "finetuned", "rlhf", "huggingface",
    "hugging face", "transformers library",
    "function calling", "tool calling", "multi-agent", "multi agent",
    "autonomous agent", "ai agent", "agentic workflow", "agentic ai",
    "semantic search", "rag pipeline", "rag system", "retrieval-augmented",
    "diffusion model", "stable diffusion",
    "speech-to-text model", "text-to-speech model",
}

# Generic hosted-provider API / raw model names. On their own these only show
# "knows an API/model exists," not "built something with it" -- a bare
# skills-list mention ("Skills: Python, OpenAI API") is too easy to pad and
# must NOT count alone. They only count as AI evidence when an
# implementation-context word (built, used, chatbot, pipeline, ...) appears
# within the same small nearby window handled by find_ambiguous_hits --
# e.g. "Built a chatbot using the OpenAI API" clears the bar, a bare list
# entry does not.
_AI_PROVIDER_IMPLEMENTATION_CONTEXT = {
    "built", "build", "building", "used", "using", "implement", "integrat",
    "deploy", "created", "create", "develop", "design", "leverag", "power",
    "pipeline", "backend", "chatbot", "agent", "rag", "assistant", "wrapper",
    "app", "application", "tool", "service", "generat", "summariz", "prompt",
}

AI_PROVIDER_API_TERMS: dict[str, set[str]] = {
    term: _AI_PROVIDER_IMPLEMENTATION_CONTEXT
    for term in (
        "openai api", "anthropic api", "gemini api", "claude api",
        "whisper api", "gpt-4", "gpt-3", "gpt4", "gpt3",
    )
}

# Ambiguous acronyms/words that only count as AI evidence when another
# AI-context word appears within a small nearby window (guards "RAG status
# report", "travel agent", "insurance agent", etc., while tolerating a PDF
# line-wrap splitting the term from its context -- see find_ambiguous_hits).
AI_AMBIGUOUS_TERMS: dict[str, set[str]] = {
    "rag": {
        "retrieval", "llm", "vector", "embed", "pipeline", "chatbot",
        "knowledge base", "generation", "augmented", "gpt", "langchain",
    },
    "agent": {
        "ai", "llm", "gpt", "autonomous", "langchain", "multi-agent",
        "tool", "pipeline", "chatbot", "genai", "openai", "crewai",
        "reasoning",
    },
    "chatbot": {
        "llm", "gpt", "openai", "nlp", "language model", "claude",
        "anthropic", "gemini", "rag", "langchain",
    },
    "agents": {
        "ai", "llm", "gpt", "autonomous", "langchain", "multi-agent",
        "tool", "pipeline", "chatbot", "genai", "openai", "crewai",
        "reasoning",
    },
}

# Generic/classic ML words: NOT sufficient on their own for eligibility
# (assignment explicitly calls these out), but still contribute to scoring
# depth once a candidate is already eligible via a strong/ambiguous+context hit.
AI_GENERIC_TERMS = {
    "machine learning", "artificial intelligence", "deep learning",
    "neural network", "neural networks", "nlp", "natural language processing",
    "computer vision", "generative ai", "genai",
}

# --- Backend / engineering depth (non-AI) -----------------------------------
BACKEND_ENGINEERING_TERMS = {
    "rest api", "restful api", "graphql", "microservice", "microservices",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "sqlite",
    "websocket", "unit test", "unit testing", "ci/cd", "system design",
    "database schema", "orm", "authentication", "oauth", "jwt",
    "api gateway", "message queue", "rabbitmq", "kafka",
}

CLOUD_DEPLOYMENT_TERMS = {
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "github actions", "vercel", "render.com", "heroku", "netlify",
    "lambda", "ec2", "s3", "cloud run", "firebase", "supabase", "nginx",
    "railway.app", "fly.io", "ci/cd pipeline", "load balancer",
}

# Infra/rigor words: an AI project mentioning at least one of these reads as
# real engineering rather than a bare API call. Used for thin-wrapper penalty.
AI_INFRA_SIGNAL_TERMS = {
    "api", "backend", "database", "pipeline", "evaluation", "eval",
    "deployed", "deployment", "fastapi", "flask", "vector", "retrieval",
    "fine-tun", "dataset", "embedding", "integration", "production",
    "scalable", "latency", "docker", "kubernetes", "endpoint",
}

# --- General tech vocabulary (language-agnostic; used for skills listing) --
GENERAL_SKILLS = {
    "java", "javascript", "typescript", "react", "react.js", "next.js",
    "node.js", "express.js", "angular", "vue.js", "c++", "c#", "golang",
    "go", "rust", "sql", "nosql", "html", "css", "tailwind", "git", "linux",
    "bash", "shell scripting", "flutter", "kotlin", "swift", "r", "matlab",
    "scala", "php", "ruby", "ruby on rails", "spring boot", ".net", "c",
    "tableau", "power bi", "excel", "figma",
}

TUTORIAL_PENALTY_TERMS = {
    "tutorial", "following a tutorial", "udemy", "coursera", "freecodecamp",
    "bootcamp project", "guided project", "course project", "clone of",
    "cloned from", "todo app", "weather app", "calculator app",
    "portfolio template",
}
