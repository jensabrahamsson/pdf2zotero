#!/usr/bin/env python3
"""
pdf2zotero.py — Convert scholarly PDFs to Zotero-importable BibTeX.

Workflow:
1. Send the PDF to a running GROBID server.
2. Extract DOI and bibliographic metadata from GROBID TEI XML.
3. If metadata is thin (common for books/reports), fill from the PDF Info dictionary.
4. If a DOI is found (GROBID or Crossref search), request BibTeX from doi.org.
5. Otherwise, generate a BibTeX entry from available metadata
   (@article, @book, or @techreport).

Requires only Python 3.9+ and a running GROBID service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
USER_AGENT = "pdf2zotero/1.2 (https://github.com/jensabrahamsson/pdf2zotero; mailto:noreply@example.com)"
# Crossref match: reject weak hits (reviews/book chapters that only mention the title).
CROSSREF_MIN_SCORE = 20.0

REPORT_HINT_RE = re.compile(
    r"\b("
    r"report|rapport|technical\s+report|tech\.?\s*report|tech\s*rep\.?|"
    r"working\s+paper|discussion\s+paper|research\s+report|research\s+paper|"
    r"white\s+paper|policy\s+(?:brief|paper|report)|occasional\s+paper|"
    r"staff\s+report|issue\s+brief|briefing\s+paper|"
    r"utredning|promemoria|\bpm\b|memo(?:randum)?|"
    r"guidelines?|handbook"
    r")\b",
    re.IGNORECASE,
)
BOOK_HINT_RE = re.compile(
    r"\b(monograph|textbook|edited\s+volume|anthology|festschrift)\b",
    re.IGNORECASE,
)
REPORT_NUMBER_RE = re.compile(
    r"\b(?:"
    r"(?:report|rapport|tech\.?\s*rep\.?|tr|wp|working\s*paper|no\.?|nr\.?)"
    r"[\s_#-]*"
    r")([A-Z]{0,6}\d[\w./-]{1,20})\b",
    re.IGNORECASE,
)

CROSSREF_BOOK_TYPES = frozenset(
    {"book", "monograph", "edited-book", "reference-book", "book-set"}
)
CROSSREF_REPORT_TYPES = frozenset(
    {"report", "report-series", "report-component"}
)


@dataclass
class Metadata:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    publisher: str = ""
    institution: str = ""
    number: str = ""  # report number
    entry_type: str = "article"  # article | book | report


def infer_entry_type(
    *,
    title: str = "",
    journal: str = "",
    publisher: str = "",
    institution: str = "",
    filename: str = "",
    hint: str = "",
) -> str:
    """Classify as article, book, or report from lightweight textual cues."""
    if journal or hint == "article":
        return "article"
    blob = " ".join(x for x in (title, publisher, institution, filename) if x)
    if hint == "report" or REPORT_HINT_RE.search(blob):
        return "report"
    if hint == "book" or BOOK_HINT_RE.search(blob):
        return "book"
    # Missing journal is normal for preprints and many OA PDFs — do not assume book.
    return "article"


def entry_type_from_crossref(work_type: str) -> str:
    work_type = (work_type or "").lower()
    if work_type in CROSSREF_BOOK_TYPES:
        return "book"
    if work_type in CROSSREF_REPORT_TYPES:
        return "report"
    if work_type in {"journal-article", "proceedings-article", "article"}:
        return "article"
    return ""


def extract_report_number(*texts: str) -> str:
    for text in texts:
        if not text:
            continue
        match = REPORT_NUMBER_RE.search(text)
        if match:
            return match.group(1).strip(" .-_/")
    return ""


def multipart_pdf(pdf_path: Path) -> tuple[bytes, str]:
    boundary = f"----pdf2zotero-{uuid.uuid4().hex}"
    filename = pdf_path.name.replace('"', "")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="input"; filename="{filename}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + pdf_path.read_bytes() + tail, boundary


def call_grobid(pdf_path: Path, grobid_url: str, timeout: int) -> bytes:
    endpoint = grobid_url.rstrip("/") + "/api/processHeaderDocument"
    body, boundary = multipart_pdf(pdf_path)
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/xml",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not contact GROBID at {endpoint}: {exc}\n"
            "Check that Docker/GROBID is running and that the port is correct."
        ) from exc


def all_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def first_text(root: ET.Element, paths: list[str]) -> str:
    for path in paths:
        text = all_text(root.find(path, TEI_NS))
        if text:
            return text
    return ""


def parse_author_nodes(author_nodes: list[ET.Element]) -> list[str]:
    authors: list[str] = []
    for author in author_nodes:
        surname = first_text(author, [".//tei:surname"])
        forenames = [
            all_text(node)
            for node in author.findall(".//tei:forename", TEI_NS)
            if all_text(node)
        ]
        name = " ".join([*forenames, surname]).strip()
        if not name:
            name = all_text(author)
        if name and name not in authors:
            authors.append(name)
    return authors


def parse_grobid_tei(xml_data: bytes) -> Metadata:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        raise RuntimeError(f"GROBID returned invalid XML: {exc}") from exc

    analytic_title = first_text(
        root,
        [
            ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title[@type='main']",
            ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title",
            ".//tei:sourceDesc//tei:analytic/tei:title[@type='main']",
            ".//tei:sourceDesc//tei:analytic/tei:title",
        ],
    )
    monogr_title = first_text(
        root,
        [
            ".//tei:sourceDesc//tei:monogr/tei:title[@level='m']",
            ".//tei:sourceDesc//tei:monogr/tei:title[@type='main']",
            ".//tei:sourceDesc//tei:monogr/tei:title",
        ],
    )
    journal = first_text(
        root,
        [".//tei:sourceDesc//tei:monogr/tei:title[@level='j']"],
    )

    # Books/reports: title often on monogr; articles: analytic (+ journal level=j).
    is_monographic = bool(monogr_title) and not journal and not analytic_title
    if is_monographic:
        title = monogr_title
    else:
        title = analytic_title or monogr_title

    author_nodes = root.findall(
        ".//tei:teiHeader/tei:fileDesc/tei:sourceDesc//tei:analytic/tei:author",
        TEI_NS,
    )
    if not author_nodes:
        author_nodes = root.findall(
            ".//tei:sourceDesc//tei:monogr/tei:author",
            TEI_NS,
        )
    if not author_nodes:
        author_nodes = root.findall(
            ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author",
            TEI_NS,
        )
    authors = parse_author_nodes(author_nodes)

    publisher = first_text(
        root,
        [".//tei:sourceDesc//tei:monogr/tei:imprint/tei:publisher"],
    )

    date = imprint_date(root)
    year_match = re.search(r"\b(18|19|20|21)\d{2}\b", date)
    year = year_match.group(0) if year_match else ""

    scopes: dict[str, str] = {}
    for node in root.findall(".//tei:sourceDesc//tei:imprint/tei:biblScope", TEI_NS):
        unit = (node.get("unit") or "").lower()
        value = all_text(node) or node.get("from", "")
        if unit and value:
            scopes[unit] = value
        if unit in {"page", "pp"} and node.get("from"):
            value = node.get("from", "")
            if node.get("to") and node.get("to") != value:
                value += f"--{node.get('to')}"
            scopes["page"] = value

    doi = ""
    for node in root.findall(".//tei:idno", TEI_NS):
        node_type = (node.get("type") or "").lower()
        text = all_text(node)
        if node_type == "doi" and text:
            doi = text
            break
        match = DOI_RE.search(text)
        if match:
            doi = match.group(0)
            break

    report_number = scopes.get("report") or scopes.get("issue") or scopes.get("number") or ""
    entry_type = infer_entry_type(
        title=title,
        journal=journal,
        publisher=publisher,
        hint="report" if REPORT_HINT_RE.search(title or monogr_title or "") else (
            "book" if is_monographic else ""
        ),
    )
    if journal:
        entry_type = "article"

    return Metadata(
        title=title,
        authors=authors,
        journal=journal,
        year=year,
        volume=scopes.get("volume", ""),
        issue=scopes.get("issue", scopes.get("number", "")),
        pages=scopes.get("page", scopes.get("pp", "")),
        doi=clean_doi(doi),
        publisher=publisher,
        institution=publisher if entry_type == "report" else "",
        number=report_number if entry_type == "report" else "",
        entry_type=entry_type,
    )


def imprint_date(root: ET.Element) -> str:
    """Prefer published date; use @when when present on the chosen node only."""
    paths = [
        ".//tei:sourceDesc//tei:imprint/tei:date[@type='published']",
        ".//tei:sourceDesc//tei:imprint/tei:date",
    ]
    for path in paths:
        node = root.find(path, TEI_NS)
        if node is None:
            continue
        when = (node.get("when") or "").strip()
        if when:
            return when
        text = all_text(node)
        if text:
            return text
    return ""


def clean_doi(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    match = DOI_RE.search(value)
    return match.group(0).rstrip(".,;:)]}") if match else ""


def decode_pdf_literal(raw: bytes) -> str:
    """Decode a PDF literal string body (content between parentheses)."""
    out = bytearray()
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x5C and i + 1 < len(raw):  # backslash
            nxt = raw[i + 1]
            escapes = {
                ord("n"): 10,
                ord("r"): 13,
                ord("t"): 9,
                ord("b"): 8,
                ord("f"): 12,
                ord("("): ord("("),
                ord(")"): ord(")"),
                ord("\\"): ord("\\"),
            }
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:  # octal
                j = i + 1
                octal = b""
                while j < len(raw) and len(octal) < 3 and 0x30 <= raw[j] <= 0x37:
                    octal += bytes([raw[j]])
                    j += 1
                out.append(int(octal, 8) & 0xFF)
                i = j
                continue
            out.append(nxt)
            i += 2
            continue
        out.append(b)
        i += 1

    data = bytes(out)
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="replace").strip()
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace").strip()
    return data.decode("utf-8", errors="replace").strip()


def decode_pdf_hex_string(hex_body: bytes) -> str:
    hex_digits = re.sub(rb"[^0-9A-Fa-f]", b"", hex_body)
    if len(hex_digits) % 2:
        hex_digits += b"0"
    try:
        data = bytes.fromhex(hex_digits.decode("ascii"))
    except ValueError:
        return ""
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="replace").strip()
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace").strip()
    return data.decode("utf-8", errors="replace").strip()


def pdf_info_value(data: bytes, key: str) -> str:
    """Extract /Key value from a PDF Info-style dictionary (best effort, stdlib)."""
    # /Title (....)  or /Title <....>  or /Title /Name
    pattern = re.compile(
        rf"/{re.escape(key)}\s*(?:\((?P<lit>(?:\\.|[^\\)])*)\)|<(?P<hex>[0-9A-Fa-f\s]+)>|(?P<name>/[^\s/\[\]()<>]+))".encode(
            "ascii"
        ),
        re.DOTALL,
    )
    match = pattern.search(data)
    if not match:
        return ""
    if match.group("lit") is not None:
        return decode_pdf_literal(match.group("lit"))
    if match.group("hex") is not None:
        return decode_pdf_hex_string(match.group("hex"))
    if match.group("name"):
        name = match.group("name").decode("ascii", errors="replace")
        return name[1:].replace("#20", " ").strip()
    return ""


def extract_pdf_info(pdf_path: Path) -> Metadata:
    """Read Title/Author/etc. from the PDF document information dictionary."""
    data = pdf_path.read_bytes()
    # Prefer the Info object if trailer points at it; otherwise scan whole file.
    info_blob = data
    trailer_match = re.search(rb"/Info\s+(\d+)\s+\d+\s+R", data)
    if trailer_match:
        obj_num = trailer_match.group(1).decode("ascii")
        obj_match = re.search(
            rf"{obj_num}\s+\d+\s+obj\s*(<<.*?>>)".encode("ascii"),
            data,
            re.DOTALL,
        )
        if obj_match:
            info_blob = obj_match.group(1)

    title = pdf_info_value(info_blob, "Title")
    author_raw = pdf_info_value(info_blob, "Author")
    authors: list[str] = []
    if author_raw:
        # "A and B" / "A; B" / "A, B" (simple split; last form is ambiguous)
        parts = re.split(r"\s+and\s+|;|/", author_raw)
        authors = [p.strip() for p in parts if p.strip()]

    # CreationDate often like D:20070315134241
    date_raw = pdf_info_value(info_blob, "CreationDate") or pdf_info_value(
        info_blob, "ModDate"
    )
    year = ""
    year_match = re.search(r"(18|19|20|21)\d{2}", date_raw)
    if year_match:
        year = year_match.group(0)

    entry_type = infer_entry_type(title=title, filename=pdf_path.name) if title else "article"

    return Metadata(
        title=title,
        authors=authors,
        year=year,
        number=extract_report_number(title, pdf_path.name),
        entry_type=entry_type,
    )


def metadata_from_filename(pdf_path: Path) -> Metadata:
    """Parse light cues from names like 'Karen Barad_2007_Meeting the Universe…'."""
    stem = pdf_path.stem
    year = ""
    year_match = re.search(r"\b((?:18|19|20|21)\d{2})\b", stem)
    if year_match:
        year = year_match.group(1)

    authors: list[str] = []
    title = ""
    # Author_Year_Title
    m = re.match(
        r"^(?P<author>.+?)[_\s]+(?P<year>(?:18|19|20|21)\d{2})[_\s]+(?P<title>.+)$",
        stem,
    )
    if m:
        authors = [m.group("author").replace("_", " ").strip()]
        year = m.group("year")
        title = m.group("title").replace("_", " ").strip()
        title = re.sub(r"\s*-\s*Quantum\s*Ph\.?$", "", title, flags=re.I).strip()
    else:
        title = stem.replace("_", " ").strip()

    entry_type = infer_entry_type(title=title, filename=stem)
    return Metadata(
        title=title if m else (title if entry_type == "report" else ""),
        authors=authors,
        year=year,
        number=extract_report_number(stem, title),
        entry_type=entry_type if (m or entry_type == "report") else "article",
    )


def merge_metadata(base: Metadata, *extras: Metadata) -> Metadata:
    """Fill empty fields on base from extras, in order."""
    out = Metadata(
        title=base.title,
        authors=list(base.authors),
        journal=base.journal,
        year=base.year,
        volume=base.volume,
        issue=base.issue,
        pages=base.pages,
        doi=base.doi,
        publisher=base.publisher,
        institution=base.institution,
        number=base.number,
        entry_type=base.entry_type,
    )
    type_rank = {"article": 0, "book": 1, "report": 2}
    for extra in extras:
        if not out.title and extra.title:
            out.title = extra.title
        if not out.authors and extra.authors:
            out.authors = list(extra.authors)
        if not out.journal and extra.journal:
            out.journal = extra.journal
        if not out.year and extra.year:
            out.year = extra.year
        if not out.volume and extra.volume:
            out.volume = extra.volume
        if not out.issue and extra.issue:
            out.issue = extra.issue
        if not out.pages and extra.pages:
            out.pages = extra.pages
        if not out.doi and extra.doi:
            out.doi = extra.doi
        if not out.publisher and extra.publisher:
            out.publisher = extra.publisher
        if not out.institution and extra.institution:
            out.institution = extra.institution
        if not out.number and extra.number:
            out.number = extra.number
        # Prefer more specific non-article types when there is no journal.
        if not out.journal and type_rank.get(extra.entry_type, 0) > type_rank.get(
            out.entry_type, 0
        ):
            out.entry_type = extra.entry_type
    if out.journal:
        out.entry_type = "article"
    elif out.entry_type not in {"book", "report"}:
        out.entry_type = infer_entry_type(
            title=out.title,
            journal=out.journal,
            publisher=out.publisher,
            institution=out.institution,
        )
    if out.entry_type == "report" and not out.institution and out.publisher:
        out.institution = out.publisher
    if out.entry_type == "report" and not out.number:
        out.number = extract_report_number(out.title, out.issue)
    return out


def normalize_title(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def title_similarity(a: str, b: str) -> float:
    """Title match score in [0, 1] (Jaccard + containment of the shorter title)."""
    na = normalize_title(a)
    nb = normalize_title(b)
    ta = set(na.split())
    tb = set(nb.split())
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    # Full title vs short catalog title: "Meeting the Universe Halfway" ⊂ long title.
    if na in nb or nb in na:
        return max(jaccard, 0.92)
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    coverage = len(shorter & longer) / len(shorter)
    return max(jaccard, coverage * 0.9)


def author_surnames(names: list[str]) -> set[str]:
    return {
        re.sub(r"\W+", "", part.split()[-1]).lower()
        for part in names
        if part and part.split()
    }


def crossref_item_surnames(item: dict) -> set[str]:
    surnames: set[str] = set()
    for author in item.get("author") or []:
        family = (author.get("family") or "").strip()
        if family:
            surnames.add(re.sub(r"\W+", "", family).lower())
    return surnames


def _crossref_query_items(params: dict, timeout: int) -> list[dict]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    return payload.get("message", {}).get("items") or []


def crossref_find_doi(metadata: Metadata, timeout: int) -> tuple[str, str]:
    """
    Search Crossref by title/author. Returns (doi, work_type) or ("", "").
    """
    if not metadata.title:
        return "", ""

    query = metadata.title
    if metadata.authors:
        query = f"{metadata.title} {metadata.authors[0]}"

    params: dict[str, str] = {
        "query.bibliographic": query,
        "rows": "8",
        "select": "DOI,title,author,type,score,published-print,published-online",
    }
    # Bias Crossref toward the expected genre.
    if metadata.entry_type == "book":
        params["filter"] = "type:book,type:monograph,type:edited-book"
    elif metadata.entry_type == "report":
        params["filter"] = "type:report,type:report-series,type:report-component"

    try:
        items = _crossref_query_items(params, timeout)
        # If typed filter returned nothing useful, retry unfiltered.
        if not items and "filter" in params:
            params.pop("filter", None)
            items = _crossref_query_items(params, timeout)
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        raise RuntimeError(f"Crossref search failed: {exc}") from exc

    best_doi = ""
    best_type = ""
    best_rank = -1.0
    want_authors = author_surnames(metadata.authors)
    monographic = metadata.entry_type in {"book", "report"}

    for item in items:
        doi = clean_doi(item.get("DOI") or "")
        if not doi:
            continue
        titles = item.get("title") or []
        item_title = titles[0] if titles else ""
        score = float(item.get("score") or 0)
        sim = title_similarity(metadata.title, item_title)
        work_type = (item.get("type") or "").lower()
        item_authors = crossref_item_surnames(item)

        # Articles need stronger title agreement than monographs (short shared tokens
        # otherwise match unrelated books — seen on arXiv preprints).
        min_sim = 0.45
        if metadata.entry_type == "article":
            min_sim = 0.62
        if score < CROSSREF_MIN_SCORE or sim < min_sim:
            continue

        # Author must match when both sides have person-authors (avoids reviews).
        # Reports may list only an institution — allow empty Crossref authors then.
        if want_authors and item_authors and not (want_authors & item_authors):
            continue

        if monographic and work_type == "journal-article":
            continue

        # Never attach a book/monograph DOI to a plain article/preprint unless
        # title match is near-exact and authors agree.
        if metadata.entry_type == "article" and work_type in CROSSREF_BOOK_TYPES:
            if sim < 0.92 or not (want_authors and item_authors and (want_authors & item_authors)):
                continue
        # Chapters/components/supplements often share tokens with papers — skip for articles.
        if metadata.entry_type == "article" and work_type in {
            "book-chapter",
            "component",
            "reference-entry",
            "dataset",
            "peer-review",
        }:
            continue

        if metadata.entry_type == "book" and work_type not in CROSSREF_BOOK_TYPES:
            if sim < 0.85 or not (want_authors & item_authors):
                continue
        if metadata.entry_type == "report" and work_type not in CROSSREF_REPORT_TYPES:
            # Accept book/monograph only if title is almost exact (wrong genre bias).
            if work_type in CROSSREF_BOOK_TYPES and sim >= 0.9:
                pass
            elif sim < 0.85 or not (want_authors & item_authors):
                continue

        type_bonus = 0.0
        if work_type in CROSSREF_BOOK_TYPES:
            type_bonus = 0.35 if metadata.entry_type == "book" else 0.05
        if work_type in CROSSREF_REPORT_TYPES:
            type_bonus = 0.4 if metadata.entry_type == "report" else 0.15
        if work_type == "journal-article" and monographic:
            type_bonus = -1.0

        rank = sim + type_bonus + min(score, 100.0) / 500.0
        if rank > best_rank:
            best_rank = rank
            best_doi = doi
            best_type = work_type

    return best_doi, best_type


def fetch_bibtex_for_doi(doi: str, timeout: int) -> str:
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/()")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/x-bibtex",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace").strip()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DOI lookup failed for {doi}: {exc}") from exc

    if not text.startswith("@"):
        raise RuntimeError(f"DOI resolver did not return BibTeX for {doi}.")
    return text + "\n"


def bib_escape(value: str) -> str:
    return (
        value.replace("\\", r"\textbackslash{}")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("#", r"\#")
    )


def zotero_file_field(pdf_path: Path) -> str:
    """JabRef/Zotero file attachment value: :/abs/path:application/pdf"""
    return f":{pdf_path.resolve()}:application/pdf"


def attach_file_to_bibtex(bibtex: str, pdf_path: Path) -> str:
    """Ensure BibTeX entry links the local PDF (insert or replace file field)."""
    file_value = bib_escape(zotero_file_field(pdf_path))
    if re.search(r"(?im)^\s*file\s*=", bibtex):
        return re.sub(
            r"(?is)(file\s*=\s*\{).*?(\})",
            rf"\1{file_value}\2",
            bibtex,
            count=1,
        )

    text = bibtex.rstrip()
    if not text.endswith("}"):
        return bibtex if bibtex.endswith("\n") else bibtex + "\n"

    head = text[:-1].rstrip()
    if head and not head.endswith((",", "{")):
        head += ","
    return head + f"\n  file = {{{file_value}}}\n}}\n"


def citation_key(metadata: Metadata, pdf_path: Path) -> str:
    surname = "unknown"
    if metadata.authors:
        surname = re.sub(r"\W+", "", metadata.authors[0].split()[-1]).lower() or "unknown"
    year = metadata.year or "nd"
    title_word = next(
        (re.sub(r"\W+", "", word).lower() for word in metadata.title.split() if len(word) > 3),
        "",
    )
    if title_word:
        return f"{surname}{year}{title_word}"
    digest = hashlib.sha1(str(pdf_path).encode()).hexdigest()[:6]
    return f"{surname}{year}{digest}"


def bibtex_entry_name(entry_type: str) -> str:
    if entry_type == "book":
        return "book"
    if entry_type == "report":
        return "techreport"
    return "article"


def fallback_bibtex(metadata: Metadata, pdf_path: Path) -> str:
    fields: list[tuple[str, str]] = []
    if metadata.authors:
        fields.append(("author", " and ".join(metadata.authors)))
    if metadata.title:
        fields.append(("title", metadata.title))
    if metadata.entry_type == "book":
        if metadata.publisher:
            fields.append(("publisher", metadata.publisher))
    elif metadata.entry_type == "report":
        institution = metadata.institution or metadata.publisher
        if institution:
            fields.append(("institution", institution))
        if metadata.number:
            fields.append(("number", metadata.number))
        fields.append(("type", "Report"))
    elif metadata.journal:
        fields.append(("journal", metadata.journal))
    if metadata.year:
        fields.append(("year", metadata.year))
    if metadata.volume and metadata.entry_type == "article":
        fields.append(("volume", metadata.volume))
    if metadata.issue and metadata.entry_type == "article":
        fields.append(("number", metadata.issue))
    if metadata.pages:
        fields.append(("pages", metadata.pages))
    if metadata.doi:
        fields.append(("doi", metadata.doi))

    fields.append(("file", zotero_file_field(pdf_path)))
    key = citation_key(metadata, pdf_path)
    entry = bibtex_entry_name(metadata.entry_type)
    lines = [f"@{entry}{{{key},"]
    for index, (name, value) in enumerate(fields):
        comma = "," if index < len(fields) - 1 else ""
        lines.append(f"  {name} = {{{bib_escape(value)}}}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def convert_one(
    pdf_path: Path,
    output_path: Path,
    grobid_url: str,
    timeout: int,
    no_doi_lookup: bool,
    save_tei: bool,
) -> str:
    xml_data = call_grobid(pdf_path, grobid_url, timeout)
    if save_tei:
        output_path.with_suffix(".tei.xml").write_bytes(xml_data)

    metadata = parse_grobid_tei(xml_data)
    pdf_meta = extract_pdf_info(pdf_path)
    name_meta = metadata_from_filename(pdf_path)
    metadata = merge_metadata(metadata, pdf_meta, name_meta)

    # Books/reports / thin GROBID output: resolve DOI via Crossref when possible.
    if not metadata.doi and not no_doi_lookup and metadata.title:
        try:
            found_doi, work_type = crossref_find_doi(metadata, timeout)
            if found_doi:
                metadata.doi = found_doi
                mapped = entry_type_from_crossref(work_type)
                if mapped:
                    metadata.entry_type = mapped
                print(
                    f"Note: resolved DOI via Crossref: {found_doi} ({work_type or 'unknown type'})",
                    file=sys.stderr,
                )
        except RuntimeError as exc:
            print(f"Warning: {exc}", file=sys.stderr)

    source = "GROBID/PDF fallback"

    if metadata.doi and not no_doi_lookup:
        try:
            bibtex = attach_file_to_bibtex(
                fetch_bibtex_for_doi(metadata.doi, timeout), pdf_path
            )
            source = f"DOI metadata ({metadata.doi})"
        except RuntimeError as exc:
            print(f"Warning: {exc}; using local metadata.", file=sys.stderr)
            bibtex = fallback_bibtex(metadata, pdf_path)
    else:
        bibtex = fallback_bibtex(metadata, pdf_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(bibtex, encoding="utf-8")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert scholarly PDFs (articles, books, and reports) "
            "to Zotero-importable BibTeX."
        )
    )
    parser.add_argument("pdfs", nargs="+", type=Path, help="One or more PDF files")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output .bib file; only valid with one input PDF",
    )
    parser.add_argument(
        "--grobid-url",
        default="http://localhost:8070",
        help="GROBID base URL (default: http://localhost:8070)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Network timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--no-doi-lookup",
        action="store_true",
        help="Do not contact doi.org/Crossref; build BibTeX only from local metadata",
    )
    parser.add_argument(
        "--save-tei",
        action="store_true",
        help="Also save GROBID's TEI XML beside the .bib file",
    )
    args = parser.parse_args()

    if args.output and len(args.pdfs) != 1:
        parser.error("--output can only be used with one PDF")

    failed = 0
    for pdf_path in args.pdfs:
        if not pdf_path.is_file():
            print(f"Error: file not found: {pdf_path}", file=sys.stderr)
            failed += 1
            continue
        if pdf_path.suffix.lower() != ".pdf":
            print(f"Error: not a PDF: {pdf_path}", file=sys.stderr)
            failed += 1
            continue

        output_path = args.output or pdf_path.with_suffix(".bib")
        try:
            source = convert_one(
                pdf_path=pdf_path,
                output_path=output_path,
                grobid_url=args.grobid_url,
                timeout=args.timeout,
                no_doi_lookup=args.no_doi_lookup,
                save_tei=args.save_tei,
            )
            print(f"{pdf_path} -> {output_path} [{source}]")
        except (OSError, RuntimeError) as exc:
            print(f"Error processing {pdf_path}: {exc}", file=sys.stderr)
            failed += 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
