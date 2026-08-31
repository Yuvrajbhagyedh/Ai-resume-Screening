"""Stage 1: discover resume files in the input folder.

Unsupported file types are skipped with a log line, not an error -- ingestion
never fails the batch over a stray .png or .zip sitting in the folder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from resume_screener.models import FileKind

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: dict[str, FileKind] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
}


@dataclass
class DiscoveredFile:
    path: Path
    kind: FileKind


def discover_resumes(input_dir: Path) -> list[DiscoveredFile]:
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    discovered: list[DiscoveredFile] = []
    for path in sorted(input_dir.iterdir()):
        if not path.is_file():
            continue
        kind = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
        if kind is None:
            logger.info("Skipping unsupported file: %s", path.name)
            continue
        discovered.append(DiscoveredFile(path=path, kind=kind))
    return discovered
