from resume_screener.extraction.info import (
    build_candidate,
    extract_email,
    extract_github_url,
    extract_name,
    extract_projects,
    extract_skills,
    split_sections,
)


def test_extract_email():
    assert extract_email("Contact: jane.doe+resume@example.com") == "jane.doe+resume@example.com"
    assert extract_email("No email here") is None


def test_extract_github_url_normalizes_and_ignores_reserved_paths():
    assert extract_github_url("GitHub: github.com/janedoe") == "https://github.com/janedoe"
    assert extract_github_url("https://www.github.com/janedoe/some-repo") == "https://github.com/janedoe"
    assert extract_github_url("See github.com/sponsors for info") is None
    assert extract_github_url("no github here") is None


def test_extract_name_from_first_lines():
    text = "Jane Doe\nSoftware Engineer\njane@example.com"
    assert extract_name(text) == "Jane Doe"


def test_extract_name_ignores_header_words():
    text = "Resume\nJohn Smith\njohn@example.com"
    assert extract_name(text) == "John Smith"


def test_extract_name_returns_none_when_no_name_line():
    text = "info@example.com\n555-1234"
    assert extract_name(text) is None


def test_split_sections_groups_by_header():
    text = "Jane Doe\n\nSkills\nPython, SQL\n\nProjects\nCool Project\n- did a thing"
    sections = split_sections(text)
    assert "python" in sections["skills"].lower()
    assert "cool project" in sections["projects"].lower()
    assert "jane doe" in sections["preamble"].lower()


def test_extract_skills_combines_vocab_and_section_tokens():
    text = "Skills\nPython, Tableau, Docker\n\nProjects\nUsed React for frontend."
    sections = split_sections(text)
    skills = extract_skills(text, sections)
    lowered = {s.lower() for s in skills}
    assert "python" in lowered
    assert "docker" in lowered
    assert "tableau" in lowered  # free-text token outside vocab, still captured
    assert "react" in lowered  # vocab hit outside the skills section


def test_extract_projects_parses_title_and_technologies():
    text = "Resume Screener | Python, FastAPI\n- Built a RAG pipeline with LangChain\n- Deployed on AWS"
    projects = extract_projects(text)
    assert len(projects) == 1
    assert projects[0].name == "Resume Screener"
    assert "fastapi" in projects[0].technologies
    assert projects[0].evidence  # python + ai evidence captured per-project


def test_wrapped_bullet_line_stays_in_same_project():
    """A wrapped continuation line (no bullet marker, follows an unfinished
    bullet) must merge into the current project, not spawn a phantom one."""
    text = (
        "RAG Assistant | Python, LangChain\n"
        "- Built a retrieval augmented generation pipeline using LangChain\n"
        "  and a vector database for semantic search over documents.\n"
        "- Deployed on AWS with Docker.\n"
    )
    projects = extract_projects(text)
    assert len(projects) == 1
    assert projects[0].name == "RAG Assistant"
    assert "vector database" in projects[0].description.lower()
    assert "vector database" in projects[0].technologies


def test_distinct_projects_still_separated_after_wrap_fix():
    """A genuinely new project (following a *finished* bullet) must still
    start its own block -- the wrap fix shouldn't merge everything."""
    text = (
        "Project One | Python\n"
        "- Did something first.\n"
        "Project Two | Python\n"
        "- Did something second.\n"
    )
    projects = extract_projects(text)
    assert len(projects) == 2
    assert projects[0].name == "Project One"
    assert projects[1].name == "Project Two"


def test_build_candidate_end_to_end():
    text = (
        "Jane Doe\n"
        "jane@example.com\n"
        "github.com/janedoe\n\n"
        "Skills\nPython, LangChain, Docker\n\n"
        "Projects\n"
        "RAG Assistant | Python, LangChain\n"
        "- Built a retrieval augmented generation pipeline\n"
    )
    candidate = build_candidate(text)
    assert candidate.name == "Jane Doe"
    assert candidate.email == "jane@example.com"
    assert candidate.github_url == "https://github.com/janedoe"
    assert "python" in [s.lower() for s in candidate.skills]
    assert candidate.projects
