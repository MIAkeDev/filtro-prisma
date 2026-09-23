"""Exercise real Streamlit reruns, uploads and manual column recovery."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def upload(content: bytes, name: str = "papers.csv") -> BytesIO:
    file = BytesIO(content)
    file.name = name
    return file


def test_clean_initial_screen():
    app = AppTest.from_file(APP, default_timeout=15).run()
    assert not app.exception
    assert not app.error
    assert len(app.dataframe) == 0
    assert app.button[0].disabled
    assert app.title[0].value == "PRISMA Paper Assistant"
    assert st.get_option("client.toolbarMode") == "viewer"


def test_upload_process_filters_downloads_and_session_reuse():
    content = upload(b"Title,Year,DOI,Abstract\nPaper A,2025,10.1/a,First\nPaper B,2024,,Second\nPaper A,2025,10.1/a,First\n")
    with patch("streamlit.file_uploader", return_value=content):
        app = AppTest.from_file(APP, default_timeout=15).run()
        app.button[0].click().run()
        assert not app.exception
        assert [metric.value for metric in app.metric] == ["3", "1", "2", "2", "3"]
        exports = app.session_state["prisma_exports"]
        assert exports["csv"].startswith(b"\xef\xbb\xbf")
        assert exports["excel"].startswith(b"PK")
        assert len(app.get("download_button")) == 3
        with patch("processor.process_dataframe", side_effect=AssertionError("Repeated processing")), patch("processor.export_excel", side_effect=AssertionError("Repeated export")):
            app.text_input(key="prisma_filter_search").set_value("Paper B").run()
            assert not app.exception
            assert len(app.dataframe[-1].value) == 1
            assert app.session_state["prisma_exports"]["csv"] == exports["csv"]
            app.selectbox(key="prisma_filter_doi").select("Con DOI").run()
            assert not app.exception
            assert any("No hay registros" in message.value for message in app.info)


def test_unknown_columns_manual_recovery():
    with patch("streamlit.file_uploader", return_value=upload(b"Unusual header,Other header\nPaper,Summary\n")):
        app = AppTest.from_file(APP, default_timeout=15).run()
        app.button[0].click().run()
        assert not app.exception
        assert len(app.warning) == 1
        app.selectbox(key="prisma_map_Titulo").select("Unusual header")
        app.selectbox(key="prisma_map_Resumen").select("Other header")
        next(button for button in app.button if button.label == "Aplicar y reprocesar").click().run()
        assert not app.exception
        assert app.session_state["prisma_result"].clean.loc[0, "Titulo"] == "Paper"


def test_corrupt_upload_is_a_friendly_error():
    with patch("streamlit.file_uploader", return_value=upload(b"corrupt", "broken.xlsx")):
        app = AppTest.from_file(APP, default_timeout=15).run()
        app.button[0].click().run()
        assert not app.exception
        assert "Excel" in app.error[0].value


@pytest.mark.parametrize("name,content", [
    ("papers.ris", b"TY  - JOUR\nT1  - Rainfall\nDO  - 10.1000/rain\nER  -"),
    ("papers.bib", b"@article{rain, title={Rainfall}, doi={10.1000/rain}}"),
    ("papers.txt", b"Ana Lee,\nRainfall,\nHydrology,\n2026,\nhttps://doi.org/10.1000/rain\nAbstract: A study."),
])
def test_new_upload_formats(name, content):
    with patch("streamlit.file_uploader", return_value=upload(content, name)) as uploader:
        app = AppTest.from_file(APP, default_timeout=15).run()
        assert {"ris", "bib", "bibtex", "txt"}.issubset(uploader.call_args.kwargs["type"])
        app.button[0].click().run()
        assert not app.exception
        assert not app.error
        assert app.session_state["prisma_result"].clean.loc[0, "DOI"] == "10.1000/rain"
        assert len(app.get("download_button")) == 3


def test_pasted_mixed_references_and_input_mode_reset():
    example = Path(__file__).parent / "fixtures" / "sciencedirect_mixed.txt"
    app = AppTest.from_file(APP, default_timeout=15).run()
    app.radio(key="input_mode").set_value("Pegar referencias").run()
    app.text_area(key="citation_text").set_value(example.read_text(encoding="utf-8")).run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.error
    assert app.session_state["prisma_result"].metrics["Duplicados encontrados"] == 2
    app.radio(key="input_mode").set_value("Subir archivo").run()
    assert not app.exception
    assert len(app.metric) == 0
