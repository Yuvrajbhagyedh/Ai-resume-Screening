from resume_screener.extraction.info import build_candidate
from resume_screener.models import GitHubEnrichment, GitHubRepoSummary, ScoreBreakdown
from resume_screener.scoring.deterministic import DeterministicScorer

scorer = DeterministicScorer()


def _score(text: str, github: GitHubEnrichment | None = None) -> ScoreBreakdown:
    candidate = build_candidate(text)
    return scorer.score(candidate, text, github or GitHubEnrichment(status="no_url"))


def test_score_is_deterministic_for_same_input():
    text = """
    Skills: Python, FastAPI, LangChain, Docker

    Projects
    RAG Chatbot - retrieval augmented generation pipeline with LangChain,
    a vector database, and a FastAPI backend deployed on AWS.
    """
    first = _score(text)
    second = _score(text)
    assert first.total == second.total
    assert first.model_dump() == second.model_dump()


def test_deep_ai_project_scores_higher_than_thin_wrapper():
    deep_text = """
    Skills: Python, FastAPI, LangChain, PyTorch, Docker

    Projects
    RAG Research Assistant - built a production RAG pipeline with LangChain,
    a vector database for retrieval, fine-tuned embeddings, evaluation
    scripts, and a FastAPI backend deployed on AWS with Docker.
    """
    thin_text = """
    Skills: Python

    Projects
    AI Project - used the OpenAI API to answer questions.
    """
    deep_score = _score(deep_text)
    thin_score = _score(thin_text)
    assert deep_score.total > thin_score.total


def test_thin_llm_wrapper_penalty_applied():
    text = """
    Skills: Python

    Projects
    Simple AI Tool - used the OpenAI API to summarize text.
    """
    score = _score(text)
    reasons = [p.reason for p in score.penalties]
    assert any("Thin LLM-wrapper" in r for r in reasons)
    assert score.penalty_total < 0


def test_thin_ai_project_penalized_despite_unrelated_backend_elsewhere():
    """The thin-wrapper infra check must be scoped near the AI mention --
    an unrelated, genuinely strong backend section elsewhere in the resume
    must not rescue a thin/one-off AI mention from the harshest penalty."""
    text = """
    Skills: Python

    Projects
    Personal AI Tool
    - Played around with an LLM to generate text for fun.




    Experience
    Backend Intern
    - Built and deployed a production REST API backend with a PostgreSQL database,
      Docker containers, and a CI/CD pipeline on AWS.
    """
    score = _score(text)
    thin = next((p for p in score.penalties if "Thin LLM-wrapper" in p.reason), None)
    assert thin is not None
    assert thin.points == -15.0


def test_tutorial_style_project_penalized():
    text = """
    Skills: Python, LangChain

    Projects
    Built an LLM chatbot with LangChain following a Udemy tutorial course project.
    """
    score = _score(text)
    reasons = [p.reason for p in score.penalties]
    assert any("Tutorial-style" in r for r in reasons)


def test_score_never_exceeds_100_or_drops_below_0():
    text = """
    Skills: Python, FastAPI, Django, LangChain, LlamaIndex, PyTorch, TensorFlow,
    Docker, Kubernetes, AWS, GCP, React, Next.js, Node.js

    Projects
    RAG Agent Platform - agentic AI system with LangChain, autonomous agents,
    fine-tuning, vector database, RAG pipeline, embeddings, FastAPI backend,
    unit tests, CI/CD, deployed on AWS with Docker and Kubernetes.
    """
    github = GitHubEnrichment(
        status="ok",
        username="dev",
        public_repos=50,
        followers=100,
        top_repos=[GitHubRepoSummary(name="repo", stars=100)],
    )
    score = _score(text, github)
    assert 0.0 <= score.total <= 100.0


def test_component_scores_respect_max_caps():
    text = "Skills: Python\nProjects\nLLM agent with RAG."
    score = _score(text)
    assert score.ai_agentic_rag_depth <= 40.0
    assert score.python_backend_engineering <= 30.0
    assert score.cloud_deployment_fullstack <= 15.0
    assert score.github_activity <= 10.0
    assert score.engineering_depth <= 5.0


def test_github_activity_scores_zero_when_unavailable():
    text = "Skills: Python\nProjects\nLLM agent with RAG."
    score = _score(text, GitHubEnrichment(status="not_found"))
    assert score.github_activity == 0.0
