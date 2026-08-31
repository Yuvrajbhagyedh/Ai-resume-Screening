import pymupdf

from resume_screener.eligibility import evaluate_eligibility
from resume_screener.extraction.document import extract_pdf
from resume_screener.extraction.integrity import analyze_spans


def _save_pdf(tmp_path, name, draw_fn):
    doc = pymupdf.open()
    page = doc.new_page()
    draw_fn(page)
    path = tmp_path / name
    doc.save(str(path))
    doc.close()
    return path


def test_white_text_is_flagged_and_excluded_from_clean_text(tmp_path):
    def draw(page):
        page.insert_text((72, 72), "Jane Doe", fontsize=12, color=(0, 0, 0))
        page.insert_text((72, 90), "Skills: Python, LangChain, RAG pipeline", fontsize=11, color=(0, 0, 0))
        page.insert_text((72, 700), "Kubernetes Azure GCP expert Kubernetes", fontsize=8, color=(1, 1, 1))

    path = _save_pdf(tmp_path, "hidden.pdf", draw)
    extracted = extract_pdf(path)
    report, clean_text, suspicious_text = analyze_spans(extracted.spans)

    assert "white_or_near_background_text" in report.flags
    assert report.suspicious_span_count > 0
    assert "kubernetes" not in clean_text.lower()
    assert "kubernetes" in suspicious_text.lower()
    assert "python" in clean_text.lower()


def test_off_page_text_is_flagged_and_excluded_from_clean_text(tmp_path):
    def draw(page):
        page.insert_text((72, 72), "Jane Doe - Python Developer", fontsize=12, color=(0, 0, 0))
        # just above the top edge of the page (y=0) -- outside the visible area
        page.insert_text((72, -50), "Docker Terraform Kafka expert", fontsize=8, color=(0, 0, 0))

    path = _save_pdf(tmp_path, "offpage.pdf", draw)
    extracted = extract_pdf(path)
    report, clean_text, suspicious_text = analyze_spans(extracted.spans)

    assert "text_outside_page_bounds" in report.flags
    assert "terraform" not in clean_text.lower()
    assert "terraform" in suspicious_text.lower()


def test_no_flags_for_normal_visible_text(tmp_path):
    def draw(page):
        page.insert_text((72, 72), "Jane Doe - Python Developer", fontsize=12, color=(0, 0, 0))

    path = _save_pdf(tmp_path, "clean.pdf", draw)
    extracted = extract_pdf(path)
    report, clean_text, _ = analyze_spans(extracted.spans)

    assert report.flags == []
    assert report.suspicious_span_count == 0
    assert "python" in clean_text.lower()


def test_integrity_flag_present_does_not_by_itself_change_eligibility_or_reject():
    """A flag is informational only -- it must not gate eligibility. Only the
    *content* of hidden text is excluded, never the candidate outright."""

    def draw(page):
        page.insert_text((72, 72), "Jane Doe", fontsize=12, color=(0, 0, 0))
        page.insert_text((72, 90), "Skills: Python, LangChain, RAG pipeline retrieval", fontsize=11, color=(0, 0, 0))
        page.insert_text((72, 700), "Java Java Java stuffed keywords", fontsize=8, color=(1, 1, 1))

    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _save_pdf(pathlib.Path(tmp), "flagged.pdf", draw)
        extracted = extract_pdf(path)
        report, clean_text, _ = analyze_spans(extracted.spans)

    assert report.flags  # integrity issue exists...
    result = evaluate_eligibility(clean_text)
    assert result.eligible  # ...but eligibility is decided purely from clean_text


def test_hidden_ai_keyword_stuffing_does_not_grant_eligibility():
    """AI evidence that exists only inside a hidden/suspicious span must not
    count toward eligibility."""

    def draw(page):
        page.insert_text((72, 72), "Jane Doe", fontsize=12, color=(0, 0, 0))
        page.insert_text((72, 90), "Skills: Python", fontsize=11, color=(0, 0, 0))
        page.insert_text(
            (72, 700),
            "LLM RAG LangChain agentic fine-tuning vector database",
            fontsize=8,
            color=(1, 1, 1),
        )

    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _save_pdf(pathlib.Path(tmp), "stuffed.pdf", draw)
        extracted = extract_pdf(path)
        report, clean_text, suspicious_text = analyze_spans(extracted.spans)

    assert report.flags
    assert "langchain" in suspicious_text.lower()
    result = evaluate_eligibility(clean_text)
    assert not result.eligible  # AI evidence was only in the hidden span
