"""Readers for RIS, BibTeX and the structured text citation exported by ScienceDirect.

These readers return source columns; the shared processor remains responsible for
normalization, deduplication, metrics and exports. No reader accesses the network.
"""

from __future__ import annotations

import re

import pandas as pd
from pybtex.database import parse_string
from pybtex.exceptions import PybtexError

from utils import MARKDOWN_LINK_PATTERN, normalize_text, unwrap_link


class CitationParseError(ValueError):
    """Expected, user-correctable errors in a citation export."""


RIS_TAG = re.compile(r"(?m)(?:^[ \t]*|(?<=[ \t]))([A-Z][A-Z0-9])[ \t]{2,}-[ \t]*")
BIB_START = re.compile(r"@([a-zA-Z]+)\s*([{(])")
DOI_URL = re.compile(r"https?://(?:dx\.)?doi\.org/\S+", re.IGNORECASE)
DOI_VALUE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


def _first(fields: dict[str, list[str]], *tags: str) -> str:
    for tag in tags:
        if any(fields.get(tag, [])):
            return " ".join(fields[tag])
    return ""


def _ris_record(text: str, start: int) -> tuple[dict[str, str], int]:
    """Consume one TY…ER record, including repeated and inline tags."""
    matches = RIS_TAG.finditer(text, start)
    previous = next(matches, None)
    if previous is None or previous.group(1) != "TY":
        raise CitationParseError("El registro RIS debe comenzar con TY  - y terminar con ER  -.")
    fields: dict[str, list[str]] = {}
    for current in matches:
        fields.setdefault(previous.group(1), []).append(normalize_text(text[previous.end():current.start()]))
        tag = current.group(1)
        if tag == "TY":
            raise CitationParseError("Falta ER  - antes del siguiente registro RIS. Vuelve a exportar el archivo completo.")
        if tag == "ER":
            first_page, last_page = _first(fields, "SP"), _first(fields, "EP")
            pages = f"{first_page}-{last_page}" if first_page and last_page and first_page != last_page else first_page or last_page
            record = {
                "Title": _first(fields, "T1", "TI", "CT"),
                "Authors": "; ".join(fields.get("AU") or fields.get("A1", [])),
                "Year": _first(fields, "PY", "Y1", "DA"),
                "DOI": _first(fields, "DO"),
                "Abstract": _first(fields, "AB", "N2"),
                "Keywords": "; ".join(fields.get("KW", [])),
                "Journal": _first(fields, "JO", "JF", "T2", "JA", "BT"),
                "URL": _first(fields, "UR", "L2"),
                "Document Type": _first(fields, "TY"),
                "Affiliations": _first(fields, "AD", "C1"),
                "Volume": _first(fields, "VL"), "Issue": _first(fields, "IS"),
                "Pages": pages, "ISSN": _first(fields, "SN"),
                "Book Series Title": _first(fields, "T3"),
                "Publication Date": _first(fields, "DA"),
            }
            if not any(record[field] for field in ("Title", "DOI", "Authors")):
                raise CitationParseError("El registro RIS no contiene título, DOI ni autores.")
            return {key: value for key, value in record.items() if value}, current.end()
        previous = current
    raise CitationParseError("El registro RIS está incompleto: falta ER  -. Incluye el registro completo.")


def _repair_bibtex_links(text: str) -> str:
    """Restore braces displaced into link labels when BibTeX is pasted as Markdown."""
    pattern = re.compile(r"(\b(?:doi|url)\s*=\s*\{[ \t]*)" + MARKDOWN_LINK_PATTERN, re.IGNORECASE)
    return pattern.sub(lambda match: match.group(1) + match.group(3) + ("}" if match.group(2).endswith("}") else ""), text)


def _bib_entry_end(text: str, start: int) -> int:
    """Find a balanced entry boundary; nested braces and quoted values are allowed."""
    match = BIB_START.match(text, start)
    if match is None:
        raise CitationParseError("No se reconoce el inicio de la entrada BibTeX.")
    opening = match.group(2)
    base = 1 if opening == "{" else 0
    depth, quoted, index = base, False, match.end()
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "%" and depth == base and not quoted:
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline + 1
            continue
        if char == '"' and depth == base:
            quoted = not quoted
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if opening == "{" and depth == 0 and not quoted:
                return index + 1
            if depth < 0:
                break
        elif char == ")" and opening == "(" and depth == 0 and not quoted:
            return index + 1
        index += 1
    raise CitationParseError("La entrada BibTeX está incompleta o tiene llaves/comillas sin cerrar. Vuelve a exportarla.")


def _skip_comments(text: str, start: int) -> int:
    """Skip whitespace and BibTeX line comments between entries."""
    while start < len(text):
        if text[start].isspace():
            start += 1
        elif text[start] == "%":
            end = text.find("\n", start)
            start = len(text) if end == -1 else end + 1
        else:
            break
    return start


def _bibtex_records(text: str, start: int) -> tuple[list[dict[str, str]], int]:
    """Parse consecutive BibTeX entries with Pybtex, preserving macro context."""
    end = start
    while True:
        next_start = _skip_comments(text, end)
        if not BIB_START.match(text, next_start):
            break
        end = _bib_entry_end(text, next_start)
    try:
        database = parse_string(text[start:end], "bibtex")
    except (PybtexError, UnicodeError, RecursionError) as exc:
        raise CitationParseError("El BibTeX no pudo interpretarse. Revisa llaves, comillas, claves repetidas y macros, o vuelve a exportarlo.") from exc
    records = []
    for entry in database.entries.values():
        fields = entry.fields
        def value(*names: str) -> str:
            return next((fields[name] for name in names if normalize_text(fields.get(name, ""))), "")

        record = {
            "Title": value("title"),
            "Authors": "; ".join(str(person) for person in entry.persons.get("author", [])),
            "Year": value("year", "date"),
            "DOI": value("doi"),
            "Abstract": value("abstract", "summary", "description"),
            "Keywords": value("keywords", "keyword"),
            "Journal": value("journal", "journaltitle", "booktitle"),
            "URL": value("url"),
            "Document Type": entry.type,
            "Affiliations": value("affiliation", "affiliations"),
            "Volume": value("volume"), "Issue": value("number", "issue"),
            "Pages": value("pages", "eid"), "ISSN": value("issn"),
            "Book Series Title": value("series"), "Publication Date": value("date"),
        }
        if not any(record[field] for field in ("Title", "DOI", "Authors")):
            raise CitationParseError("Una entrada BibTeX no contiene título, DOI ni autores.")
        records.append({key: value for key, value in record.items() if value})
    if not records:
        raise CitationParseError("El BibTeX no contiene referencias bibliográficas.")
    return records, end


def _sciencedirect_record(text: str) -> dict[str, str]:
    """Read the authors/title/source/year/DOI layout of Export citation to text.

    A plain prose citation without this structure is rejected rather than guessed.
    Abstracts are taken as a whole and are never searched for publication years.
    """
    marker = re.search(r"(?im)^[ \t]*(Abstract|Keywords):[ \t]*", text)
    header = text[:marker.start()] if marker else text
    body = text[marker.start():] if marker else ""
    lines = [normalize_text(line).rstrip(",") for line in header.splitlines() if line.strip()]
    year_index = next((index for index, line in enumerate(lines) if re.fullmatch(r"(?:1[5-9]|20|21)\d{2}", line)), None)
    if len(lines) < 4 or year_index is None or year_index < 3:
        raise CitationParseError("El texto no coincide con una cita exportada por ScienceDirect. Usa RIS/BibTeX o conserva las líneas de autores, título, publicación y año del texto original.")
    # The first three lines are defined by this export format, not inferred from
    # arbitrary prose. Wrapped or differently styled citations need RIS/BibTeX.
    record = {"Authors": lines[0], "Title": lines[1], "Journal": lines[2], "Year": lines[year_index]}
    if year_index + 1 < len(lines):
        pages = re.fullmatch(r"(?i)(?:pages?\s+|pp?\.?\s*)?([a-z]?\d+(?:\s*[-–—]\s*[a-z]?\d+)?)", lines[year_index + 1])
        if pages:
            record["Pages"] = pages.group(1)
    for line in lines[3:]:
        volume = re.fullmatch(r"(?i)Volume\s+(.+?)(?:,\s*Issue\s+(.+))?", line)
        issue = re.fullmatch(r"(?i)(?:Issue|Number)\s+(.+)", line)
        issn = re.fullmatch(r"(?i)ISSN\s+(.+)", line)
        if volume:
            record["Volume"] = volume.group(1)
            if volume.group(2):
                record["Issue"] = volume.group(2)
        elif issue:
            record["Issue"] = issue.group(1)
        elif issn:
            record["ISSN"] = issn.group(1)
        candidate = re.sub(r"(?i)^doi\s*:\s*", "", line)
        if candidate.startswith("(") and candidate.endswith(")"):
            candidate = candidate[1:-1]
        candidate = unwrap_link(candidate)
        if DOI_URL.fullmatch(candidate) or DOI_VALUE.fullmatch(candidate):
            record["DOI"] = candidate.rstrip(".,;")
        elif re.fullmatch(r"https?://\S+", candidate):
            record["URL"] = candidate.rstrip(".,;")
    keywords = re.search(r"(?im)^[ \t]*Keywords:[ \t]*", body)
    abstract = re.match(r"(?i)Abstract:[ \t]*", body)
    if abstract:
        record["Abstract"] = body[abstract.end():keywords.start() if keywords else len(body)].strip()
    if keywords:
        record["Keywords"] = body[keywords.end():].strip()
    return record


def read_citations(text: str, expected: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Read one or more citations, including concatenated export formats in TXT.

    Explicit RIS/BIB extensions require their stated format. TXT and pasted text
    are detected by content. Every nonempty part must parse; none is discarded.
    """
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^```(?:ris|bibtex|bib|text)?[ \t]*\n?|^```[ \t]*$", "", text).strip()
    if not text:
        raise CitationParseError("No hay referencias para procesar. Sube un archivo o pega una cita completa.")
    if "\x00" in text:
        raise CitationParseError("El archivo no contiene texto bibliográfico válido. Expórtalo como UTF-8.")
    text = _repair_bibtex_links(text)
    records, formats = [], []
    position = 0
    while position < len(text):
        position = _skip_comments(text, position)
        if position == len(text):
            break
        tag = RIS_TAG.match(text, position)
        if tag and tag.group(1) == "TY":
            record, end = _ris_record(text, position)
            batch, file_format = [record], "RIS"
        elif BIB_START.match(text, position):
            batch, end = _bibtex_records(text, position)
            file_format = "BibTeX"
        else:
            # Separate standard plain-text citations at blank lines preceding
            # the next authors/title/source/year header, not inside abstracts.
            boundary = re.compile(r"\n[ \t]*\n(?=[^\n]+,\n[^\n]+,\n[^\n]+,\n(?:(?:Volume|Issue|Number) [^\n]+,\n)*(?:1[5-9]|20|21)\d{2},?\n)|\n(?=TY[ \t]{2,}-|@[a-zA-Z]+\s*[{(])").search(text, position)
            end = boundary.start() if boundary else len(text)
            if end == position:
                raise CitationParseError("No se reconoce el formato de las referencias.")
            batch, file_format = [_sciencedirect_record(text[position:end])], "Texto ScienceDirect"
        if expected and file_format != expected:
            raise CitationParseError(f"El contenido no corresponde al formato {expected}. Guarda el contenido mixto como TXT o pega las referencias.")
        records.extend(batch)
        if file_format not in formats:
            formats.append(file_format)
        position = end
    if not records:
        raise CitationParseError("No se encontraron referencias bibliográficas.")
    return pd.DataFrame(records).fillna(""), {"citation_format": " + ".join(formats)}
