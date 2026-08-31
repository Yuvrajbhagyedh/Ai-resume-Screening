from resume_screener.eligibility import evaluate_eligibility


def test_eligible_with_python_skill_and_llm_project():
    text = """
    Jane Doe
    Skills: Python, SQL, React

    Projects
    RAG Chatbot - Built a retrieval augmented generation pipeline using LangChain
    and a vector database to answer questions over internal docs.
    """
    result = evaluate_eligibility(text)
    assert result.eligible
    assert result.python_evidence
    assert result.ai_evidence
    assert result.rejection_reasons == []


def test_python_evidence_via_framework_alone_counts():
    text = """
    Skills: FastAPI, Docker

    Projects
    Autonomous research agent using LangChain tool calling and OpenAI API.
    """
    result = evaluate_eligibility(text)
    assert result.eligible
    assert any(h.term == "fastapi" for h in result.python_evidence)


def test_python_evidence_via_work_experience_counts():
    text = """
    Experience
    Backend Intern -- wrote data pipelines in Python for the analytics team.

    Projects
    LLM-powered support agent built with LangChain and a RAG pipeline.
    """
    result = evaluate_eligibility(text)
    assert result.eligible
    assert any(h.term == "python" for h in result.python_evidence)


def test_rejected_without_python_evidence():
    text = """
    Skills: Java, React, Next.js

    Projects
    Built an LLM-powered agent using LangChain and a RAG pipeline.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible
    assert not result.python_evidence
    assert any("Python" in r for r in result.rejection_reasons)


def test_rejected_without_ai_evidence():
    text = """
    Skills: Python, Django, PostgreSQL

    Projects
    Built a REST API backend for an e-commerce platform.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible
    assert not result.ai_evidence


def test_generic_ai_words_alone_do_not_satisfy_eligibility():
    text = """
    Skills: Python, Machine Learning, AI, Deep Learning

    Summary
    Passionate about artificial intelligence and machine learning.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible
    assert not result.ai_evidence


def test_ambiguous_rag_without_context_does_not_satisfy_eligibility():
    text = """
    Skills: Python

    Experience
    Tracked project status using a RAG (red/amber/green) reporting sheet.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible


def test_ambiguous_rag_with_context_satisfies_eligibility():
    text = """
    Skills: Python

    Projects
    Built a RAG system over company documents using a vector store for retrieval.
    """
    result = evaluate_eligibility(text)
    assert result.eligible


def test_ambiguous_agent_word_alone_does_not_satisfy():
    text = """
    Skills: Python

    Experience
    Worked as a customer support agent handling client escalations.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible


def test_javascript_java_react_do_not_disqualify_when_python_and_ai_present():
    text = """
    Skills: Python, JavaScript, Java, React, Next.js

    Projects
    Full-stack app with a Next.js frontend and a Python FastAPI backend
    exposing an LLM-powered agent built with LangChain.
    """
    result = evaluate_eligibility(text)
    assert result.eligible


# --- Regression: ambiguous-term context split across PDF-wrapped lines -----


def test_ambiguous_rag_context_split_across_wrapped_lines_satisfies_eligibility():
    """A PDF line-wrap can split "RAG system ... using a" from "vector store
    for retrieval." onto separate lines -- the context word must still be
    found in the small window around the term, not just on its exact line."""
    text = """
    Skills: Python

    Projects
    Built a RAG system over company documents using a
    vector store for retrieval.
    """
    result = evaluate_eligibility(text)
    assert result.eligible


def test_ambiguous_rag_context_far_away_still_does_not_satisfy_eligibility():
    """The windowed context check stays conservative: a context word two or
    more lines away must not manufacture eligibility for an unrelated
    ambiguous-acronym mention."""
    text = """
    Skills: Python

    Experience
    Tracked project status using a RAG report for the sprint.
    Nothing else related appears on this line.
    Two lines later we mention vector embeddings for search, unrelated to the above.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible


# --- Regression: tightened AI eligibility bar -------------------------------


def test_interested_in_ai_statement_alone_does_not_satisfy_eligibility():
    text = """
    Skills: Python

    Summary
    I am interested in AI and hope to work in the field of artificial intelligence.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible
    assert not result.ai_evidence


def test_bare_openai_api_skill_mention_alone_does_not_satisfy_eligibility():
    """A provider API name in a plain skills list, with no nearby
    implementation language, must not count as meaningful AI evidence."""
    text = """
    Skills: Python, OpenAI API, Docker

    Projects
    E-commerce Backend
    - Built a REST API backend for an e-commerce platform.
    """
    result = evaluate_eligibility(text)
    assert not result.eligible
    assert not result.ai_evidence


def test_openai_api_with_implementation_context_satisfies_eligibility():
    """The same provider API name, described as part of an actual build,
    does count."""
    text = """
    Skills: Python

    Projects
    Customer Support Bot
    - Built a chatbot using the OpenAI API to answer support tickets automatically.
    """
    result = evaluate_eligibility(text)
    assert result.eligible


def test_bare_gpt4_skill_mention_alone_does_not_satisfy_eligibility():
    text = """
    Skills: Python, GPT-4, Docker
    """
    result = evaluate_eligibility(text)
    assert not result.eligible


def test_langchain_and_langgraph_bare_skill_mentions_count_as_ai_evidence():
    """Named agentic frameworks count unconditionally, even as a bare skill
    listing -- unlike generic provider API names above."""
    text = """
    Skills: Python, LangChain, LangGraph

    Projects
    Simple Script
    - A basic script.
    """
    result = evaluate_eligibility(text)
    assert result.eligible
    assert any(h.term == "langchain" for h in result.ai_evidence)
    assert any(h.term == "langgraph" for h in result.ai_evidence)


def test_google_adk_bare_skill_mention_counts_as_ai_evidence():
    text = "Skills: Python, Google ADK\n"
    result = evaluate_eligibility(text)
    assert result.eligible
    assert any(h.term == "google adk" for h in result.ai_evidence)
