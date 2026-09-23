# PRISMA Paper Assistant

Aplicación local en Python y Streamlit para limpiar exportaciones bibliográficas y preparar una base de trabajo para el screening de una revisión sistemática. No requiere cuentas, base de datos, APIs ni claves.

## Qué hace

- Lee CSV y XLSX con detección automática de columnas bibliográficas, además de RIS, BibTeX y citas TXT de ScienceDirect.
- Permite pegar referencias directamente y reconoce los tres formatos de citas por su contenido, incluso combinados.
- Reconoce encabezados habituales de SpringerLink, Scopus, Web of Science, IEEE, ScienceDirect, Dimensions, Crossref y exportaciones similares, además de variantes en español. La compatibilidad depende de los encabezados del archivo; no se conecta a esas plataformas.
- Detecta CSV separados por coma, punto y coma o tabulación; intenta UTF-8/UTF-8-SIG, Windows-1252 y Latin-1.
- Limpia espacios, saltos de línea y valores nulos; normaliza DOI y extrae años.
- Identifica duplicados por DOI o título normalizado y conserva la primera aparición.
- Presenta métricas, búsqueda literal, rango de años y filtros por presencia de DOI y abstract.
- Exporta una base limpia, un resumen PRISMA y un informe de duplicados con su motivo.
- Permite corregir las columnas cuando la detección automática no reconoce el formato.

La herramienta prepara los registros. No decide qué artículos incluir, no valida metadatos contra fuentes externas y no sustituye la revisión del investigador.

## Instalación

Requiere **Python 3.11 o posterior**. Las dependencias directas están fijadas en `requirements.txt`. La validación local se realizó con Python 3.14.3.

```bash
python -m venv .venv
```

Activa el entorno en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

En macOS o Linux:

```bash
source .venv/bin/activate
```

Instala y ejecuta:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Si PowerShell impide activar el entorno, no es necesario cambiar su política: utiliza directamente el intérprete del proyecto.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit muestra la dirección local de la aplicación, normalmente `http://localhost:8501`.

## Uso

1. Sube una exportación CSV, XLSX, RIS, BIB/BIBTEX o TXT de hasta 50 MB. En CSV/Excel, los encabezados deben estar en la primera fila no vacía. También puedes elegir **Pegar referencias** para ingresar RIS, BibTeX o texto de ScienceDirect.
2. Presiona **Procesar archivo** o **Procesar referencias**, según el modo elegido.
3. Revisa las métricas y **Ver columnas detectadas**. Si es necesario, activa **Corregir asignación de columnas** y presiona **Aplicar y reprocesar**.
4. Explora la base limpia, todos los registros o los duplicados. Puedes mostrar 25, 50, 100 o todos los resultados.
5. Descarga los archivos y completa las decisiones de screening en tu hoja de cálculo.

Los filtros afectan únicamente la vista: todas las descargas contienen sus bases completas. La lectura, el procesamiento y la generación de archivos se realizan una vez por acción de procesamiento; los filtros reutilizan los resultados de la sesión.

### Archivos descargables

| Archivo | Contenido |
| --- | --- |
| `papers_prisma_limpios.csv` | Base sin duplicados, codificada en UTF-8 con BOM. |
| `papers_prisma_limpios.xlsx` | Hojas `Papers` y `Resumen_PRISMA`. |
| `papers_duplicados.xlsx` | Hojas `Duplicados` y `Resumen_PRISMA`; incluye `Duplicado` y `Motivo_duplicado`. |

La base limpia contiene, en este orden:

```text
ID, Titulo, Autores, Año, DOI, Resumen, Palabras_clave, Revista, URL,
Tipo_documento, Afiliacion, Decision_Titulo_Resumen, Motivo_Exclusion,
Texto_Completo, Decision_Final
```

Los IDs empiezan en 1. Las cuatro columnas de screening comienzan vacías. No se incluye ninguna columna auxiliar de comparación de títulos.

### Exportaciones de SpringerLink

Se reconoce automáticamente el formato con estos encabezados:

| Columna de Springer | Campo de la base PRISMA |
| --- | --- |
| `Item Title` | `Titulo` |
| `Publication Title` | `Revista` |
| `Item DOI` | `DOI` |
| `Authors` | `Autores` |
| `Publication Year` | `Año` |
| `URL` | `URL` |
| `Content Type` | `Tipo_documento` |

`Book Series Title`, `Journal Volume` (también con espacios repetidos) y `Journal Issue` se aceptan como columnas adicionales y aparecen en el diagnóstico de columnas no exportadas; no se confunden con el título del artículo o de la revista. No forman parte del esquema PRISMA de esta versión. Si la exportación no incluye abstract, palabras clave o afiliación, esos campos quedan vacíos. Los valores de `Item DOI` se normalizan y participan en la detección de duplicados igual que los de `DOI`.

### Exportaciones de ScienceDirect y referencias pegadas

| Formato | Importación |
| --- | --- |
| RIS (`.ris`) | Registros delimitados por `TY  -` y `ER  -`. Admite autores `AU`/`A1` y palabras clave `KW` repetidos, resúmenes `AB`/`N2`, líneas de continuación y etiquetas pegadas en una misma línea. |
| BibTeX (`.bib`, `.bibtex`) | Entradas `@article`, `@book`, `@inproceedings`, etc., con autores separados por `and`, valores entre llaves o comillas, macros y múltiples entradas. |
| Texto (`.txt`) | El formato **Export citation to text** de ScienceDirect: autores, título, publicación y año en líneas separadas, DOI/URL y secciones `Abstract:` y `Keywords:`. |
| Referencias pegadas | Detección automática de RIS, BibTeX o texto de ScienceDirect. Admite los tres formatos concatenados, conservando cada aparición para el informe de duplicados. |

Los DOI y URL pegados como `[enlace](https://...)` se convierten a sus direcciones reales. En los campos DOI/URL de BibTeX también se recupera el caso en que la llave de cierre quedó dentro del texto del enlace al copiarlo. El resumen completo se conserva, normalizando únicamente sus espacios y saltos de línea.

El formato TXT admitido es el exportado por ScienceDirect, no cualquier cita redactada libremente. Para otros estilos de texto o títulos partidos en varias líneas, utiliza RIS o BibTeX. Las citas TXT múltiples deben separarse por una línea en blanco. Los registros incompletos o no interpretables muestran un error; no se ignoran silenciosamente. La extensión RIS/BIB debe corresponder a su contenido; usa TXT o el modo de pegado para combinar formatos.

Se añadió [Pybtex](https://docs.pybtex.org/api/parsing.html) como dependencia para analizar la gramática BibTeX, incluidos valores anidados, autores y macros. El análisis es completamente local. Los comandos y las llaves de protección LaTeX se conservan en los campos bibliográficos; no se ejecuta LaTeX.

El botón de despliegue y las opciones de desarrollo de Streamlit están ocultos mediante `client.toolbarMode = "viewer"`, tanto en la configuración como durante la ejecución de la interfaz.

## Reglas y límites de procesamiento

- **Datos ausentes:** se mantienen vacíos. Las filas completamente vacías se descartan. Los registros sin título ni DOI se conservan y se señalan para revisión manual.
- **Columnas repetidas:** se conservan con nombres únicos. Si varias columnas corresponden al mismo campo, se prioriza el alias preferido y se rellenan sus vacíos con las siguientes. Las columnas de palabras clave se combinan. Los campos adicionales no se exportan; se enumeran en el diagnóstico.
- **DOI:** se quitan prefijos `doi:`, `https://doi.org/`, `http://doi.org/` y variantes `dx.doi.org`; se convierten a minúsculas. No se consultan ni inventan DOI.
- **Años:** se extraen años de cuatro dígitos entre 1500 y 2199. Los valores ambiguos con años distintos quedan vacíos. Por defecto, los filtros conservan los registros sin año; puedes desactivar esa opción.
- **Duplicados:** se comparan DOI no vacíos y títulos en minúsculas, con puntuación reemplazada por espacios y espacios normalizados. Un registro se marca si cualquiera de sus claves coincide con un registro anterior, incluso si ese anterior ya fue marcado. No se realiza coincidencia aproximada ni se fusionan metadatos. Títulos idénticos pueden corresponder a trabajos distintos: revisa el informe de duplicados.
- **Métricas:** `identificados = duplicados + únicos`. Los recuentos con DOI y abstract corresponden a todos los registros identificados, incluidos los duplicados.
- **Excel de entrada:** se utiliza la primera hoja con encabezados y datos, cuyo nombre aparece en pantalla. Las demás hojas no se combinan. No se admiten `.xls` ni libros cifrados.
- **CSV incorrecto:** las filas con distinto número de columnas y las comillas mal cerradas producen un mensaje claro; no se descartan registros silenciosamente. La detección de codificación es heurística, por lo que UTF-8 es preferible al exportar.
- **Excel de salida:** los valores se escriben como texto literal, no como fórmulas. Si una celda excede 32.767 caracteres, se deshabilita esa descarga y se conserva el CSV completo. Se eliminan del XLSX los caracteres de control incompatibles con Excel. En CSV, las celdas que podrían interpretarse como fórmulas llevan un apóstrofo inicial; los registros en memoria no cambian.

## Privacidad

Los archivos y las referencias pegadas se procesan únicamente durante la sesión y no se almacenan permanentemente por la aplicación. Los resultados y las descargas se mantienen en `st.session_state`, sin caché compartida entre usuarios. Cambiar o quitar el archivo, editar el texto pegado o cambiar de modo de entrada libera los resultados anteriores.

En ejecución local, el procesamiento ocurre en tu equipo. En Streamlit Community Cloud, el navegador envía el archivo al servidor y el procesamiento ocurre en su memoria. No se envían datos a APIs de terceros. No se implementa analítica; las estadísticas de uso de Streamlit están desactivadas en `.streamlit/config.toml`.

## Estructura

```text
.
├── app.py                    # Interfaz y estado de la sesión
├── processor.py              # Lectura, detección, normalización, filtros y exportación
├── citation_readers.py       # Lectores RIS, BibTeX y texto de ScienceDirect
├── utils.py                  # Utilidades de texto y encabezados
├── requirements.txt          # Dependencias directas verificadas
├── pytest.ini
├── .gitignore
├── .streamlit/
│   └── config.toml           # Tema, límite de carga y privacidad
└── tests/
    ├── test_processor.py     # Datos, casos límite y exportaciones
    ├── test_citation_readers.py  # Formatos de citas y conservación del contenido
    ├── test_app.py           # Flujo de la interfaz con Streamlit AppTest
    └── fixtures/
        └── sciencedirect_mixed.txt  # Ejemplo suministrado para verificar los tres formatos
```

`processor.py` no depende de Streamlit. Sus funciones y `ProcessingResult` se pueden reutilizar en futuros módulos de screening, extracción de variables o generación de flujos PRISMA, sin cambiar la interfaz de lectura de archivos. Esos módulos no están implementados en esta versión.

## Pruebas

```bash
python -m pytest -q
python -m compileall -q app.py processor.py citation_readers.py utils.py
```

Las pruebas cubren separadores y codificaciones, XLSX, RIS, BibTeX, texto de ScienceDirect, archivos inválidos, campos ausentes, encabezados duplicados y desconocidos, normalización, deduplicación, filtros, exportaciones reabiertas con OpenPyXL, 10.000 registros y el flujo de Streamlit, incluidos el pegado de referencias y la recuperación mediante asignación manual. Se utilizan datos sintéticos y el ejemplo de ScienceDirect suministrado para verificar sus tres formatos.

## Despliegue en Streamlit Community Cloud

1. Sube este proyecto a un repositorio de GitHub, incluyendo `requirements.txt` y `.streamlit/config.toml`. No subas `.venv`, archivos de usuarios ni secretos.
2. En [Streamlit Community Cloud](https://share.streamlit.io/), selecciona **Create app** y elige el repositorio y la rama.
3. Indica `app.py` como archivo principal.
4. En las opciones avanzadas, selecciona una versión de Python compatible con las dependencias: 3.11 o posterior, entre las disponibles en el servicio.
5. Despliega. Las dependencias se instalan desde `requirements.txt`; no hay secretos ni servicios adicionales que configurar.

Consulta la documentación oficial de [despliegue](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) y [dependencias](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies). El proyecto está preparado para desplegarse; la validación local no implica que exista ya un despliegue público.
