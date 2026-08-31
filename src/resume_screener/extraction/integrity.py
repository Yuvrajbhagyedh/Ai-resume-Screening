"""PDF text-layer integrity analysis: detect visually-hidden or off-page text.

IMPORTANT — heuristic, not proof of intent (see README "Integrity heuristic
limitations" section). A flagged span means "this text is not visually
readable the way normal resume text is", nothing more:

  - It never causes rejection on its own.
  - It is excluded from the text handed to eligibility/scoring, so a resume
    can't game the screener by stuffing invisible keywords.
  - Flags are always surfaced in the final output for a human to review.

Detection only applies to PDFs, since DOCX/TXT extraction has no layout
information to inspect.
"""

from __future__ import annotations

from dataclasses import dataclass

from resume_screener.extraction.document import TextSpan
from resume_screener.models import IntegrityFlag, IntegrityReport

NEAR_WHITE_CHANNEL_MIN = 235  # each of R/G/B at or above this reads as "white-ish"
NEAR_ZERO_OPACITY_MAX = 0.05
TINY_FONT_MAX_PT = 1.5
OUT_OF_BOUNDS_TOLERANCE_PT = 2.0
INVISIBLE_RENDER_MODE = 3  # PDF spec: Tr 3 = neither fill nor stroke text


@dataclass
class SpanVerdict:
    span: TextSpan
    flags: list[IntegrityFlag]

    @property
    def is_suspicious(self) -> bool:
        return bool(self.flags)


def _is_near_white(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r >= NEAR_WHITE_CHANNEL_MIN and g >= NEAR_WHITE_CHANNEL_MIN and b >= NEAR_WHITE_CHANNEL_MIN


def _is_outside_page(bbox: tuple[float, float, float, float], page_rect: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    px0, py0, px1, py1 = page_rect
    return (
        x1 < px0 - OUT_OF_BOUNDS_TOLERANCE_PT
        or x0 > px1 + OUT_OF_BOUNDS_TOLERANCE_PT
        or y1 < py0 - OUT_OF_BOUNDS_TOLERANCE_PT
        or y0 > py1 + OUT_OF_BOUNDS_TOLERANCE_PT
    )


def evaluate_span(span: TextSpan) -> SpanVerdict:
    flags: list[IntegrityFlag] = []

    if _is_near_white(span.color_rgb):
        flags.append("white_or_near_background_text")

    if span.opacity is not None and span.opacity <= NEAR_ZERO_OPACITY_MAX:
        flags.append("near_zero_alpha_text")
    elif span.render_mode == INVISIBLE_RENDER_MODE:
        flags.append("near_zero_alpha_text")

    if _is_outside_page(span.bbox, span.page_rect):
        flags.append("text_outside_page_bounds")

    if 0 < span.font_size < TINY_FONT_MAX_PT:
        flags.append("abnormally_tiny_font")

    return SpanVerdict(span=span, flags=flags)


def analyze_spans(spans: list[TextSpan]) -> tuple[IntegrityReport, str, str]:
    """Return (report, clean_text, suspicious_text).

    clean_text/suspicious_text preserve original line/block structure so
    downstream regex-based extraction keeps working on clean_text.
    """
    verdicts = [evaluate_span(s) for s in spans]

    all_flags: set[IntegrityFlag] = set()
    details: list[str] = []
    suspicious_count = 0

    clean_lines: dict[tuple[int, int, int], list[str]] = {}
    suspicious_lines: dict[tuple[int, int, int], list[str]] = {}
    line_order: list[tuple[int, int, int]] = []

    for verdict in verdicts:
        s = verdict.span
        key = (s.page_index, s.block_index, s.line_index)
        if key not in clean_lines:
            clean_lines[key] = []
            suspicious_lines[key] = []
            line_order.append(key)

        if verdict.is_suspicious:
            suspicious_count += 1
            all_flags.update(verdict.flags)
            suspicious_lines[key].append(s.text)
            if len(details) < 50:
                snippet = s.text.strip()[:80]
                details.append(f"[{', '.join(verdict.flags)}] {snippet!r}")
        else:
            clean_lines[key].append(s.text)

    def _render(lines: dict[tuple[int, int, int], list[str]]) -> str:
        rendered = ["".join(lines[key]) for key in line_order if lines[key]]
        return "\n".join(rendered)

    report = IntegrityReport(
        flags=sorted(all_flags),
        suspicious_span_count=suspicious_count,
        total_span_count=len(spans),
        details=details,
    )
    return report, _render(clean_lines), _render(suspicious_lines)
