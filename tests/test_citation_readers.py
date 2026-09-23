"""End-to-end checks for the supplied ScienceDirect exports and parser edge cases."""

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from processor import FileProcessingError, export_excel, normalize_doi, process_dataframe, read_uploaded_file
from utils import normalize_text


EXAMPLE = Path(__file__).parent / "fixtures" / "sciencedirect_mixed.txt"
DOI = "10.1016/j.ejrh.2025.103046"
URL = "https://www.sciencedirect.com/science/article/pii/S2214581825008754"


def example_parts():
    ris, remainder = EXAMPLE.read_text(encoding="utf-8").split("@article{", 1)
    bibtex, plain = remainder.split("\nWentao Zhou,", 1)
    return {"ris": ris, "bib": "@article{" + bibtex, "txt": "Wentao Zhou," + plain}


@pytest.mark.parametrize("suffix", ["ris", "bib", "txt"])
def test_supplied_sciencedirect_exports(suffix):
    examples = example_parts()
    source = read_uploaded_file(examples[suffix].encode("utf-8"), f"export.{suffix}")
    result = process_dataframe(source)
    record = result.clean.iloc[0]
    assert len(result.clean) == 1
    assert record["DOI"] == DOI
    assert record["URL"] == URL
    assert record["Año"] == "2026"  # Neither the DOI's 2025 nor years in the abstract.
    assert record["Revista"] == "Journal of Hydrology: Regional Studies"
    for name in ("Wentao", "Qiang", "Jiang", "Siyu", "Bin", "Xiang", "Tao", "Fujian", "Xinyue", "Zihao"):
        assert name in record["Autores"]
    for keyword in ("Rainfall-induced debris flows", "Machine learning", "Mobilized material", "Hydrological processes", "Spatio-temporal prediction"):
        assert keyword in record["Palabras_clave"]
    expected_abstract = examples["txt"].split("Abstract: ", 1)[1].split("\nKeywords:", 1)[0]
    assert record["Resumen"] == normalize_text(expected_abstract)
    workbook = load_workbook(BytesIO(export_excel(result.clean, result.metrics)))
    assert workbook["Papers"]["E2"].value == DOI
    assert workbook["Papers"]["F2"].value == record["Resumen"]


def test_combined_example_detects_all_three_versions_and_deduplicates():
    source = read_uploaded_file(EXAMPLE.read_bytes(), "combined.txt")
    result = process_dataframe(source)
    assert source.attrs["citation_format"] == "RIS + BibTeX + Texto ScienceDirect"
    assert result.metrics["Registros identificados"] == 3
    assert result.metrics["Duplicados encontrados"] == 2
    assert result.metrics["Registros únicos"] == 1
    assert result.duplicates.Motivo_duplicado.tolist() == ["DOI y título duplicados"] * 2


def test_multiple_ris_records_continuation_and_missing_metadata():
    content = "TY  - JOUR\nTI  - Rainfall\n    prediction\nA1  - Pérez, Ana\nN2  - First line\n    Second line\nKW  - rain\nKW  - flow\nER  -\n\nTY  - BOOK\nT1  - Another paper\nER  -"
    result = process_dataframe(read_uploaded_file(content.encode("cp1252"), "export.ris"))
    assert len(result.clean) == 2
    assert result.clean.loc[0, "Titulo"] == "Rainfall prediction"
    assert result.clean.loc[0, "Autores"] == "Pérez, Ana"
    assert result.clean.loc[0, "Resumen"] == "First line Second line"
    assert result.clean.loc[0, "Palabras_clave"] == "rain; flow"
    assert result.clean.DOI.eq("").all()


def test_bibtex_nested_braces_quotes_macros_and_multiple_entries():
    content = '''% An exported bibliography
@string{journalname = "Journal"}
@article(first, title = {A {nested} title}, journal = journalname # " of Hydrology",
  author = {Doe, Jane and {Research Group}}, year = 2025,
  abstract = {Scientific {content} with commas, equals = and parentheses (x).})
@inproceedings{second, title = "Another {Title}", booktitle={Proceedings}, date={2026-02-01}}
'''
    result = process_dataframe(read_uploaded_file(content.encode(), "export.bibtex"))
    assert len(result.clean) == 2
    assert result.clean.loc[0, "Revista"] == "Journal of Hydrology"
    assert "Research Group" in result.clean.loc[0, "Autores"]
    assert "equals =" in result.clean.loc[0, "Resumen"]
    assert result.clean.loc[1, "Revista"] == "Proceedings"
    assert result.clean.loc[1, "Año"] == "2026"


@pytest.mark.parametrize("content,suffix", [
    ("TY  - JOUR\nT1  - Missing end", "ris"),
    ("TY  - JOUR\nT1  - First\nTY  - JOUR\nT1  - Second\nER  -", "ris"),
    ("TY  - JOUR\nER  -", "ris"),
    ("@article{key, title={Incomplete", "bib"),
    ('@article{key, title="Unclosed}', "bib"),
    ("@article{key, title={First}}\n@article{key, title={Second}}", "bib"),
    ("@article{key, title missing equals}", "bib"),
    ("@string{source={A journal}}", "bib"),
    ("An arbitrary prose citation that cannot be mapped reliably.", "txt"),
    ("TY  - JOUR\nT1  - Valid\nER  -\nUnreadable trailing content", "ris"),
    ("@article{key, title={Valid}}\nUnreadable trailing content", "bib"),
    ("@article{key, title={Wrong extension}}", "ris"),
])
def test_invalid_citations_are_not_silently_skipped(content, suffix):
    with pytest.raises(FileProcessingError):
        read_uploaded_file(content.encode(), f"invalid.{suffix}")


def test_multiple_sciencedirect_text_citations():
    first = example_parts()["txt"]
    second = first.replace("Machine learning enhanced framework", "Another framework").replace(DOI, "10.1000/other")
    result = process_dataframe(read_uploaded_file((first + "\n\n" + second).encode(), "export.txt"))
    assert len(result.clean) == 2
    assert result.clean.loc[1, "DOI"] == "10.1000/other"
    assert "Wentao Zhou" not in result.clean.loc[0, "Palabras_clave"]


@pytest.mark.parametrize("value", [
    "[DOI](https://doi.org/10.1000/ABC)",
    "[https://doi.org/10.1000/ABC](https://doi.org/10.1000/ABC).",
    "[DOI](https://doi.org/10.1000/ABC(1))",
    "<https://doi.org/10.1000/ABC>",
])
def test_markdown_doi_normalization_in_all_formats(value):
    expected = "10.1000/abc(1)" if "(1)" in value else "10.1000/abc"
    assert normalize_doi(value) == expected
    source = pd.DataFrame({"Title": ["First", "Second"], "Item DOI": [value, expected]})
    result = process_dataframe(source)
    assert result.records.DOI.tolist() == [expected, expected]
    assert result.records.Duplicado.tolist() == [False, True]


def test_bibtex_valid_markdown_doi_braces_are_kept_balanced():
    content = '@article{a, title={Paper}, doi={[DOI](https://doi.org/10.1000/ABC)}}'
    result = process_dataframe(read_uploaded_file(content.encode(), "export.bib"))
    assert result.clean.loc[0, "DOI"] == "10.1000/abc"
