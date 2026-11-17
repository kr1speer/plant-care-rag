"""Corpus registry loading and splitting articles into search fragments."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INTRO_SECTION = "Вступление"
METADATA_SEPARATOR = "\n---\n"
HEADING_RE = re.compile(r"^#{2,3} (.+?)\s*$")
DOC_ID_RE = re.compile(r"D\d{2}")
REGISTRY_FIELDS = ("id", "file", "title", "url")


@dataclass(frozen=True)
class Fragment:
    """One article section used as a BM25 document.

    Attributes:
        doc_id: Registry ID of the article, for example ``D05``.
        title: Article title from the registry.
        section: Section heading or ``Вступление`` for the intro.
        url: Public source URL of the article.
        text: Section text shown to users.
        search_text: Indexed text: title and section prefix plus ``text``.
    """

    doc_id: str
    title: str
    section: str
    url: str
    text: str
    search_text: str


def load_registry(data_dir: Path = DATA_DIR) -> list[dict]:
    """Read ``documents.jsonl`` and check IDs and fields.

    Args:
        data_dir: Directory with ``documents.jsonl`` and ``corpus/``.

    Returns:
        Registry entries in file order.

    Raises:
        ValueError: If an entry lacks fields, has a malformed or repeated ID.
    """
    entries = []
    seen = set()
    lines = (data_dir / "documents.jsonl").read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if not all(isinstance(entry.get(field), str) for field in REGISTRY_FIELDS):
            raise ValueError(f"documents.jsonl:{number}: missing registry fields")
        if not DOC_ID_RE.fullmatch(entry["id"]) or entry["id"] in seen:
            raise ValueError(f"documents.jsonl:{number}: bad or repeated id")
        seen.add(entry["id"])
        entries.append(entry)
    return entries


def _check_header(entry: dict, header: str) -> None:
    """Ensure the file header matches the registry title and URL.

    Args:
        entry: Registry entry of the document.
        header: File text above the metadata separator.

    Raises:
        ValueError: If the title or the source URL differs from the registry.
    """
    lines = header.splitlines()
    if not lines or lines[0] != f"# {entry['title']}":
        raise ValueError(f"{entry['file']}: title differs from registry")
    if f"Источник: {entry['url']}" not in lines:
        raise ValueError(f"{entry['file']}: source URL differs from registry")


def split_fragments(entry: dict, markdown: str) -> list[Fragment]:
    """Split one corpus file into fragments by ``##`` and ``###`` headings.

    Args:
        entry: Registry entry with ``id``, ``title`` and ``url``.
        markdown: Full file text including the metadata header.

    Returns:
        Non-empty sections in file order; the intro comes first.

    Raises:
        ValueError: If the file has no ``---`` metadata separator.
    """
    if METADATA_SEPARATOR not in markdown:
        raise ValueError(f"{entry['file']}: metadata separator not found")
    body = markdown.split(METADATA_SEPARATOR, 1)[1]
    sections: list[tuple[str, list[str]]] = [(INTRO_SECTION, [])]
    for line in body.splitlines():
        if heading := HEADING_RE.match(line):
            sections.append((heading.group(1), []))
        else:
            sections[-1][1].append(line)

    fragments = []
    for section, lines in sections:
        text = "\n".join(lines).strip()
        if text:
            fragments.append(
                Fragment(
                    doc_id=entry["id"],
                    title=entry["title"],
                    section=section,
                    url=entry["url"],
                    text=text,
                    search_text=f"{entry['title']}. {section}.\n{text}",
                )
            )
    return fragments


def load_fragments(data_dir: Path = DATA_DIR) -> list[Fragment]:
    """Load all registry documents and split them into fragments.

    Args:
        data_dir: Directory with ``documents.jsonl`` and ``corpus/``.

    Returns:
        Fragments of all documents in registry order.

    Raises:
        ValueError: If the registry is inconsistent with the corpus files.
    """
    fragments = []
    for entry in load_registry(data_dir):
        path = data_dir / "corpus" / entry["file"]
        if not path.is_file():
            raise ValueError(f"{entry['file']}: corpus file not found")
        markdown = path.read_text(encoding="utf-8")
        _check_header(entry, markdown.split(METADATA_SEPARATOR, 1)[0])
        fragments.extend(split_fragments(entry, markdown))
    return fragments
