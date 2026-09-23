"""Streamlit interface; processing and exports live in processor.py."""

import pandas as pd
import streamlit as st

from processor import (
    FIELD_LABELS,
    FIELDS,
    EXTRA_FIELDS,
    SUPPORTED_FIELDS,
    ColumnDetectionError,
    FileProcessingError,
    ProcessingResult,
    detect_columns,
    export_csv,
    export_excel,
    filter_records,
    process_dataframe,
    read_uploaded_file,
)


st.set_page_config(page_title="PRISMA Paper Assistant", page_icon="📚", layout="wide")
st.set_option("client.toolbarMode", "viewer")


def clear_session() -> None:
    """Release the previous upload and its derived data when the file changes."""
    for key in list(st.session_state):
        if key.startswith("prisma_"):
            del st.session_state[key]


def prepare_result(source: pd.DataFrame, overrides: dict | None = None) -> None:
    """Process and generate download bytes once, only after an explicit action."""
    result = process_dataframe(source, overrides)
    exports = {"csv": export_csv(result.clean)}
    export_warnings = []
    for key, frame, sheet in (
        ("excel", result.clean, "Papers"),
        ("duplicates", result.duplicates, "Duplicados"),
    ):
        try:
            exports[key] = export_excel(frame, result.metrics, sheet)
        except FileProcessingError as exc:
            export_warnings.append(str(exc))
    st.session_state.prisma_result = result
    st.session_state.prisma_exports = exports
    st.session_state.prisma_export_warnings = list(dict.fromkeys(export_warnings))
    for key in list(st.session_state):
        if key.startswith("prisma_filter_"):
            del st.session_state[key]


def show_mapping(source: pd.DataFrame, result: ProcessingResult | None) -> None:
    """Explain detection and offer a manual recovery path for unknown headers."""
    auto_mapping = detect_columns(source)
    mapping = result.mapping if result else auto_mapping
    visible_fields = FIELDS + [field for field in EXTRA_FIELDS if mapping.get(field)]
    with st.expander("Ver columnas detectadas", expanded=result is None):
        diagnostic = pd.DataFrame({
            "Campo": [FIELD_LABELS[field] for field in visible_fields],
            "Columnas del archivo": [" · ".join(mapping[field]) or "No detectado" for field in visible_fields],
        })
        st.dataframe(diagnostic, hide_index=True, width="stretch")
        assigned = {column for columns in mapping.values() for column in columns}
        unused = [str(column) for column in source.columns if column not in assigned]
        if unused:
            st.caption("Columnas adicionales no exportadas: " + ", ".join(unused))
        st.caption("Si un campo tiene varias columnas, se usa la primera con contenido. Las columnas de palabras clave se combinan.")
        if st.checkbox("Corregir asignación de columnas", value=result is None, key="prisma_manual"):
            with st.form("column_mapping"):
                st.write("Asigna únicamente los campos que necesiten corrección.")
                chosen = {}
                grid = st.columns(2)
                options = [None, *source.columns]
                for index, field in enumerate(SUPPORTED_FIELDS):
                    default = mapping[field][0] if mapping.get(field) else None
                    with grid[index % 2]:
                        chosen[field] = st.selectbox(
                            FIELD_LABELS[field], options,
                            index=options.index(default),
                            format_func=lambda value: value if value is not None else "— No asignar —",
                            key=f"prisma_map_{field}",
                        )
                if st.form_submit_button("Aplicar y reprocesar", type="primary"):
                    overrides = {
                        field: column for field, column in chosen.items()
                        if column != (auto_mapping[field][0] if auto_mapping[field] else None)
                    }
                    try:
                        with st.spinner("Normalizando registros…"):
                            prepare_result(source, overrides)
                        st.rerun()
                    except FileProcessingError as exc:
                        st.error(str(exc))


def show_results(result: ProcessingResult) -> None:
    """Render metrics, filters, preview and downloads from session-owned results."""
    st.divider()
    st.subheader("Tu base, lista para screening")
    st.caption("Se conserva la primera aparición de cada DOI o título. Revisa los duplicados antes de excluirlos de tu revisión.")
    for column, (label, value) in zip(st.columns(5), result.metrics.items()):
        with column:
            st.metric("Duplicados detectados" if label == "Duplicados encontrados" else label, f"{value:,}")
    st.caption("Las métricas de DOI y abstract se calculan sobre todos los registros identificados, incluidos los duplicados.")
    for warning in result.warnings:
        st.info(warning)

    st.subheader("Explorar registros")
    view = st.radio(
        "Base que deseas explorar", ["Base PRISMA limpia", "Todos los registros", "Duplicados"],
        horizontal=True, key="prisma_filter_view",
    )
    datasets = {"Base PRISMA limpia": result.clean, "Todos los registros": result.records, "Duplicados": result.duplicates}
    dataset = datasets[view]
    query = st.text_input(
        "Buscar en título, resumen o palabras clave", placeholder="Por ejemplo: aprendizaje automático",
        key="prisma_filter_search",
    )
    year_column, doi_column, abstract_column = st.columns([2, 1, 1])
    year_range = None
    include_unknown = True
    with year_column:
        years = pd.to_numeric(dataset["Año"], errors="coerce").dropna()
        if not years.empty:
            minimum, maximum = int(years.min()), int(years.max())
            if minimum < maximum:
                year_range = st.slider("Año de publicación", minimum, maximum, (minimum, maximum), key=f"prisma_filter_year_{view}")
            else:
                st.caption(f"Año de publicación: {minimum}")
                year_range = (minimum, maximum)
            if dataset["Año"].eq("").any():
                include_unknown = st.checkbox("Incluir registros sin año", value=True, key="prisma_filter_unknown_year")
        else:
            st.caption("No hay años disponibles para filtrar en esta vista.")
    with doi_column:
        doi = st.selectbox("Tiene DOI", ["Todos", "Con DOI", "Sin DOI"], key="prisma_filter_doi")
    with abstract_column:
        abstract = st.selectbox("Tiene abstract", ["Todos", "Con abstract", "Sin abstract"], key="prisma_filter_abstract")
    filtered = filter_records(dataset, query, year_range, doi, abstract, include_unknown)
    count_column, description_column = st.columns([1, 3])
    with count_column:
        limit = st.selectbox("Registros por vista", [25, 50, 100, "Todos"], key="prisma_filter_limit")
    preview = filtered if limit == "Todos" else filtered.head(limit)
    with description_column:
        st.caption(f"Mostrando {len(preview):,} de {len(filtered):,} coincidencias · {len(dataset):,} registros en esta base.")
    if filtered.empty:
        st.info("No hay registros que coincidan con los filtros seleccionados.")
    else:
        st.dataframe(
            preview, hide_index=True, width="stretch", height=min(620, 38 + 35 * len(preview)),
            column_config={
                "Titulo": st.column_config.TextColumn("Título", width="large"),
                "Resumen": st.column_config.TextColumn("Resumen", width="large"),
                "Palabras_clave": "Palabras clave", "Tipo_documento": "Tipo de documento",
                "Afiliacion": "Afiliación", "Motivo_duplicado": "Motivo del duplicado",
                "Serie_libro": "Serie de libros", "Numero": "Número", "Paginas": "Páginas o número de artículo",
                "Fecha_publicacion": "Fecha de publicación",
            },
        )

    st.subheader("Descargar resultados")
    st.caption("Las descargas incluyen la base completa. Los filtros solo afectan la visualización.")
    for warning in st.session_state.prisma_export_warnings:
        st.warning(warning)
    exports = st.session_state.prisma_exports
    csv_column, excel_column, duplicate_column = st.columns(3)
    with csv_column:
        st.download_button(
            "Descargar CSV", exports["csv"], "papers_prisma_limpios.csv", "text/csv",
            width="stretch", type="primary", on_click="ignore",
        )
        st.caption("Base limpia · UTF-8 compatible con Excel")
    with excel_column:
        st.download_button(
            "Descargar Excel", exports.get("excel", b""), "papers_prisma_limpios.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch", disabled="excel" not in exports, on_click="ignore",
        )
        st.caption("Base limpia + resumen PRISMA")
    with duplicate_column:
        st.download_button(
            "Descargar duplicados", exports.get("duplicates", b""), "papers_duplicados.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch", disabled="duplicates" not in exports, on_click="ignore",
        )
        st.caption("Registros repetidos + motivo de detección")


def main() -> None:
    """Run a three-step upload, process and review workflow."""
    st.markdown("""
        <style>
        .block-container { max-width: 1440px; padding-top: 2.5rem; }
        h1 { letter-spacing: -0.045em; }
        h2, h3 { letter-spacing: -0.025em; }
        [data-testid="stMetric"] { background: #F3F6F8; border-radius: 10px; padding: 16px; }
        [data-testid="stMetricValue"] { color: #087E8B; }
        </style>
    """, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("### PRISMA\nPaper Assistant")
        st.divider()
        st.markdown("**01 · Importar**\n\nArchivos bibliográficos o referencias pegadas.\n\n**02 · Preparar**\n\nMetadatos normalizados y duplicados identificados.\n\n**03 · Revisar**\n\nUna base lista para tu screening.")
        st.divider()
        st.caption("Sin cuentas · Sin claves API · Sin servicios externos de procesamiento")
        st.caption("La herramienta prepara los registros; las decisiones de inclusión y exclusión corresponden al investigador.")

    st.caption("HERRAMIENTAS PARA REVISIÓN SISTEMÁTICA")
    st.title("PRISMA Paper Assistant")
    st.markdown("**Limpieza, normalización y preparación de literatura científica para revisiones sistemáticas.**")
    st.write("Sube una exportación bibliográfica y el sistema identificará automáticamente títulos, autores, DOI, resúmenes, años, revistas y otros metadatos relevantes.")

    with st.container(border=True):
        input_mode = st.radio(
            "Importar referencias", ["Subir archivo", "Pegar referencias"],
            horizontal=True, key="input_mode", on_change=clear_session,
        )
        uploaded, pasted = None, ""
        if input_mode == "Subir archivo":
            uploaded = st.file_uploader(
                "Subir archivo bibliográfico", type=["csv", "xlsx", "ris", "bib", "bibtex", "txt"],
                help="CSV, XLSX, RIS, BibTeX o TXT · Hasta 50 MB. Detección automática de formato y codificación.",
                key="bibliographic_upload", on_change=clear_session,
            )
            st.caption("CSV · XLSX · RIS · BibTeX · TXT de citas de ScienceDirect")
        else:
            pasted = st.text_area(
                "Referencias bibliográficas", height=220,
                placeholder="Pega uno o varios registros RIS, entradas BibTeX o citas de texto de ScienceDirect.",
                key="citation_text", on_change=clear_session,
            )
            st.caption("Se conservan autores, palabras clave y resúmenes. También se aceptan enlaces pegados como Markdown.")
        ready = uploaded is not None if input_mode == "Subir archivo" else bool(pasted.strip())
        if st.button("Procesar archivo" if input_mode == "Subir archivo" else "Procesar referencias", type="primary", disabled=not ready):
            clear_session()
            try:
                with st.spinner("Leyendo y preparando tu bibliografía…"):
                    source = read_uploaded_file(uploaded) if uploaded is not None else read_uploaded_file(pasted.encode("utf-8"), "Referencias pegadas.txt")
                    st.session_state.prisma_source = source
                    prepare_result(source)
            except ColumnDetectionError as exc:
                st.warning(str(exc))
            except FileProcessingError as exc:
                st.error(str(exc))

    if "prisma_source" in st.session_state:
        source = st.session_state.prisma_source
        st.caption(
            f"Archivo: {source.attrs['filename']} · {len(source):,} registros · "
            f"{len(source.columns)} columnas · {source.attrs['file_type']}"
        )
        if "sheet" in source.attrs:
            st.caption(f"Hoja procesada: {source.attrs['sheet']}. Se utiliza la primera hoja con datos del libro.")
        elif "separator" in source.attrs:
            separator = "tabulación" if source.attrs["separator"] == "\t" else source.attrs["separator"]
            st.caption(f"Codificación: {source.attrs['encoding']} · Separador: {separator}")
        elif "citation_format" in source.attrs:
            st.caption(f"Formato detectado: {source.attrs['citation_format']} · Codificación: {source.attrs['encoding']}")
        result = st.session_state.get("prisma_result")
        show_mapping(source, result)
        result = st.session_state.get("prisma_result")
        if result is not None:
            show_results(result)
    elif not ready:
        st.markdown("#### De tu exportación a una base de trabajo")
        for column, title, description in zip(
            st.columns(3),
            ["Detección automática", "Duplicados trazables", "Screening organizado"],
            ["Reconoce los campos de diferentes bases bibliográficas.",
             "Compara DOI y títulos, y conserva un informe de los registros repetidos.",
             "Descarga una base con campos de decisión listos para completar."],
        ):
            with column:
                st.markdown(f"**{title}**")
                st.caption(description)

    st.divider()
    st.caption("Los archivos se procesan únicamente durante la sesión y no se almacenan permanentemente por la aplicación.")
    st.caption("En ejecución local, los datos permanecen en tu equipo. En un despliegue web, se procesan en la memoria del servidor que aloja la aplicación.")


if __name__ == "__main__":
    main()
