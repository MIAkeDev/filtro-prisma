"""Small, shared helpers for bibliographic text and column names."""

import re
import unicodedata
from collections import Counter

import pandas as pd


NULL_STRINGS = {"nan", "none", "null", "<na>", "nat"}
MARKDOWN_LINK_PATTERN = r"\[([^\]\r\n]*)\]\((https?://(?:[^\s()]|\([^()\s]*\))+)\)"
# Arrow-backed Pandas strings interpret \s as ASCII, unlike Python's regex.
# Include Unicode whitespace explicitly so all import formats normalize alike.
WHITESPACE_PATTERN = r"[\s" + "\u001c-\u001f\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"


def decode_text(data: bytes) -> tuple[str, str]:
    """Decode bibliographic text using the supported, ordered encoding fallbacks."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def clean_link_series(series: pd.Series) -> pd.Series:
    """Unwrap full Markdown links without changing punctuation inside their URLs."""
    values = clean_series(series)
    links = values.str.extract(r"^" + MARKDOWN_LINK_PATTERN + r"[.,;]?$", expand=True)
    return values.where(links[1].isna(), links[1]).str.replace(r"^<(.*)>$", r"\1", regex=True)


def unwrap_link(value: str) -> str:
    """Return the destination of a full Markdown link, or the original text."""
    value = normalize_text(value)
    match = re.fullmatch(MARKDOWN_LINK_PATTERN + r"[.,;]?", value)
    return match.group(2) if match else value.removeprefix("<").removesuffix(">")


def normalize_text(value: object) -> str:
    """Clean whitespace and missing values without rewriting scientific text."""
    if value is None or pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.casefold() in NULL_STRINGS else text


def clean_series(series: pd.Series) -> pd.Series:
    """Vectorized version of normalize_text for a whole bibliographic column."""
    result = series.fillna("").astype(str).str.replace(WHITESPACE_PATTERN, " ", regex=True).str.strip()
    return result.mask(result.str.casefold().isin(NULL_STRINGS), "")


def normalize_column(value: object) -> str:
    """Ignore accents, punctuation, case and spacing in column names."""
    text = unicodedata.normalize("NFKD", normalize_text(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", " ", text).strip()


def unique_headers(values: list[object]) -> list[str]:
    """Keep repeated and unnamed source columns addressable without data loss."""
    headers = [normalize_text(value) or f"Columna {i + 1}" for i, value in enumerate(values)]
    reserved = set(headers)
    used: set[str] = set()
    counts: Counter[str] = Counter()
    result = []
    for header in headers:
        counts[header] += 1
        name = header
        while name in used:
            name = f"{header} [columna {counts[header]}]"
            counts[header] += 1
            while name in reserved or name in used:
                name = f"{header} [columna {counts[header]}]"
                counts[header] += 1
        used.add(name)
        result.append(name)
    return result
