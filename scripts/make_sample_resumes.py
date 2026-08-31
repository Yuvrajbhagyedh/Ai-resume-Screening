"""Generate a small set of sample PDF resumes into ./resumes for manual CLI testing.

Not part of the shipped package -- a one-off dev script, run via:
    .venv/bin/python scripts/make_sample_resumes.py
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

OUT_DIR = Path(__file__).resolve().parent.parent / "resumes"


def write_text_pdf(path: Path, lines: list[str]) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=10, color=(0, 0, 0))
        y += 14
        if y > 800:
            page = doc.new_page()
            y = 72
    doc.save(str(path))
    doc.close()


SAMPLES: dict[str, list[str]] = {
    "01_strong_rag_engineer.pdf": [
        "Aditi Sharma",
        "aditi.sharma@example.com",
        "github.com/aditisharma-dev",
        "",
        "Skills",
        "Python, FastAPI, LangChain, PyTorch, Docker, AWS, PostgreSQL",
        "",
        "Projects",
        "Enterprise RAG Assistant | Python, LangChain, FastAPI",
        "- Built a production retrieval augmented generation pipeline using LangChain",
        "  and a Pinecone vector database over 50k internal documents.",
        "- Fine-tuned embeddings, added evaluation scripts, deployed on AWS with Docker.",
        "- Exposed the system via a FastAPI backend with unit tests and CI/CD.",
        "",
        "Autonomous Research Agent | Python, OpenAI API",
        "- Designed a multi-agent workflow with tool calling and function calling",
        "  to autonomously summarize research papers.",
        "",
        "Experience",
        "Backend Intern, Acme Corp",
        "- Built REST APIs in Python (Django) backed by PostgreSQL and Redis.",
    ],
    "02_thin_llm_wrapper.pdf": [
        "Rahul Verma",
        "rahul.verma@example.com",
        "",
        "Skills",
        "Python, HTML, CSS",
        "",
        "Projects",
        "AI Chat App",
        "- Used the OpenAI API to build a simple AI chat app.",
    ],
    "03_tutorial_clone.pdf": [
        "Priya Nair",
        "priya.nair@example.com",
        "github.com/priyanair",
        "",
        "Skills",
        "Python, LangChain, Flask",
        "",
        "Projects",
        "LLM Chatbot Clone",
        "- Followed a Udemy tutorial course project to build an LLM chatbot",
        "  with LangChain and the OpenAI API.",
    ],
    "04_js_react_but_eligible.pdf": [
        "Kevin Wu",
        "kevin.wu@example.com",
        "github.com/kevinwu",
        "",
        "Skills",
        "JavaScript, TypeScript, React, Next.js, Python, FastAPI",
        "",
        "Projects",
        "Full-Stack RAG Search Platform | Next.js, Python, FastAPI",
        "- Built a Next.js frontend backed by a Python FastAPI service implementing",
        "  a RAG pipeline with a vector database for semantic search.",
        "- Deployed on Vercel and AWS with Docker and CI/CD via GitHub Actions.",
    ],
    "05_no_python.pdf": [
        "Sara Ali",
        "sara.ali@example.com",
        "",
        "Skills",
        "Java, Spring Boot, React, Next.js",
        "",
        "Projects",
        "Agentic Support Bot | Java, LangChain4j",
        "- Built an autonomous agent with RAG and LLM tool calling in Java.",
    ],
    "06_no_ai.pdf": [
        "Tom Becker",
        "tom.becker@example.com",
        "",
        "Skills",
        "Python, Django, PostgreSQL, Docker, AWS",
        "",
        "Projects",
        "E-commerce Backend | Python, Django",
        "- Built a REST API backend for an e-commerce platform with PostgreSQL",
        "  and deployed it on AWS with Docker.",
    ],
    "07_generic_ai_buzzwords_only.pdf": [
        "Meera Iyer",
        "meera.iyer@example.com",
        "",
        "Skills",
        "Python, Machine Learning, Artificial Intelligence, Deep Learning",
        "",
        "Summary",
        "Passionate about AI and machine learning with a strong interest in data science.",
    ],
    "08_hidden_white_text.pdf": None,  # built specially below
}


def build_hidden_text_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    visible = [
        "Nina Patel",
        "nina.patel@example.com",
        "",
        "Skills",
        "Python, Flask",
        "",
        "Projects",
        "Basic Web App | Python, Flask",
        "- Built a small Flask web app for tracking tasks.",
    ]
    y = 72
    for line in visible:
        page.insert_text((72, y), line, fontsize=10, color=(0, 0, 0))
        y += 14
    # Hidden keyword-stuffing: white text, same page, meant to game keyword scanners.
    page.insert_text(
        (72, 760),
        "LLM RAG LangChain agentic fine-tuning vector database retrieval augmented generation",
        fontsize=6,
        color=(1, 1, 1),
    )
    doc.save(str(path))
    doc.close()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for filename, lines in SAMPLES.items():
        path = OUT_DIR / filename
        if lines is None:
            build_hidden_text_pdf(path)
        else:
            write_text_pdf(path, lines)
        print(f"wrote {path}")

    # A couple of malformed/unreadable files -- must not crash the batch.
    (OUT_DIR / "09_corrupt.pdf").write_bytes(b"%PDF-1.4 not a real pdf body")
    (OUT_DIR / "10_empty.pdf").write_bytes(b"")
    print(f"wrote {OUT_DIR / '09_corrupt.pdf'}")
    print(f"wrote {OUT_DIR / '10_empty.pdf'}")


if __name__ == "__main__":
    main()
