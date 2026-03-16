# CSVToCSVW

[![Publish Docker image](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/PublishContainer.yml/badge.svg)](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/PublishContainer.yml)
[![TestExamples](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/TestExamples.yml/badge.svg?branch=main)](https://github.com/Mat-O-Lab/CSVToCSVW/actions/workflows/TestExamples.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19053064.svg)](https://doi.org/10.5281/zenodo.19053064)

> Automatically convert CSV files into [W3C CSVW](https://www.w3.org/ns/csvw)-compliant JSON-LD metadata and RDF — no manual annotation required.

---

## What it does

Raw CSV files from experiments and engineering workflows carry structure and meaning that is invisible to machines. CSVToCSVW analyses a CSV file and produces:

- **CSVW JSON-LD metadata** describing table structure, column types, and units
- **RDF output** (Turtle, JSON-LD, N-Triples, …) serialising the full content as Linked Data
- **QUDT unit annotations** — physical units like `mm`, `°C`, `N·m` are resolved to their canonical [QUDT](https://qudt.org/) ontology terms
- **Open Annotation metadata** for key-value property blocks (sample metadata, instrument settings, etc.)
- **Provenance triples** (PROV-O) recording which software version generated the output

### Multi-block CSV support

Many real-world scientific CSV files contain a metadata header followed by one or more data tables — separated by blank lines, different delimiters, or a change in column count. CSVToCSVW detects and handles all blocks independently:

```csv
Sample name:   AWA_3_03           ← key-value metadata block
Machine:       INSTRON 8852TT
Temperature:   23 °C

Time,Force,Displacement           ← tabular data block
s,kN,mm
0.0,0.00,0.000
0.5,1.23,0.012
```

---

## Quick start

### Docker

```bash
docker run -p 5000:5000 ghcr.io/mat-o-lab/csvtocsvw:latest
```

Open [http://localhost:5000](http://localhost:5000) for the UI, or [http://localhost:5000/api/docs](http://localhost:5000/api/docs) for the interactive API.

### Docker Compose

```bash
git clone https://github.com/Mat-O-Lab/CSVToCSVW
cd CSVToCSVW
cp .env.example .env   # edit as needed
docker compose up
```

### Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `APP_PORT` | Host port to expose | `5000` |
| `APP_SECRET` | Secret key for session/CSRF | `changemeNOW` |
| `SERVER_URL` | Public base URL of the service | `https://csvtocsvw.matolab.org` |
| `ADMIN_MAIL` | Contact email shown in API docs | `csvtocsvw@matolab.org` |
| `APP_VERSION` | Version string injected at build time | from `settings.py` |
| `SSL_VERIFY` | Verify SSL certificates on outbound requests | `True` |

---

## API

### `POST /api/annotate`

Fetch a CSV by URL and return CSVW JSON-LD metadata.

```bash
curl -X POST "https://csvtocsvw.matolab.org/api/annotate" \
  -H "Content-Type: application/json" \
  -d '{"data_url": "https://example.org/mydata.csv"}'
```

### `POST /api/annotate_upload`

Upload a CSV file directly.

```bash
curl -X POST "https://csvtocsvw.matolab.org/api/annotate_upload" \
  -F "file=@mydata.csv"
```

### `POST /api/rdf`

Convert a CSVW metadata file (by URL) to RDF.

```bash
curl -X POST "https://csvtocsvw.matolab.org/api/rdf" \
  -H "Content-Type: application/json" \
  -d '{"metadata_url": "https://example.org/mydata-metadata.json", "format": "turtle"}'
```

Full interactive docs: [https://csvtocsvw.matolab.org/api/docs](https://csvtocsvw.matolab.org/api/docs)

---

## Jupyter notebook

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Mat-O-Lab/CSVToCSVW/blob/main/csv_parser.ipynb)

Run the notebook to process a CSV interactively — paste a URL or upload a file and download the resulting JSON-LD metadata.

---

## Example output

Given a simple property table:

```csv
Property,Value,Unit
Actuator diameter,40,mm
Rated voltage,240,V AC
Operating temp min,-25,°C
Weight,120,g
```

CSVToCSVW produces a CSVW table with QUDT-annotated columns:

```json
{
  "@type": "csvw:TableGroup",
  "tables": [{
    "url": "mydata.csv",
    "tableSchema": {
      "columns": [
        { "titles": "Property", "datatype": "string" },
        { "titles": "Value",    "datatype": "string" },
        { "titles": "Unit",     "datatype": "string" }
      ]
    }
  }]
}
```

See [`examples/`](examples/) for real input/output pairs including multi-block files.

---

## Known limitations

- All-text tables (every cell is a string) are ambiguous with key-value metadata blocks and may be classified as metadata. Columns with numeric-looking names (e.g. sensor IDs `1281068`) will be treated as headerless.

---

## Cite this software

If you use CSVToCSVW in your research, please cite it:

```text
Hanke, T., Kröcker, B., & Fechner, R. (2024). CSVToCSVW (v1.3.5).
GitHub. https://github.com/Mat-O-Lab/CSVToCSVW
```

A `CITATION.cff` file is included for automatic citation in GitHub and Zenodo.

---

## Acknowledgments

The authors would like to thank the Federal Government and the Heads of Government of the Länder for their funding and support within the framework of the [Platform Material Digital](https://www.materialdigital.de) consortium. Funded by the German [Federal Ministry of Education and Research (BMBF)](https://www.bmbf.de/bmbf/en/) through the [MaterialDigital](https://www.bmbf.de/SharedDocs/Publikationen/de/bmbf/5/31701_MaterialDigital.pdf?__blob=publicationFile&v=5) Call in Project [KupferDigital](https://www.materialdigital.de/project/1) — project id 13XP5119.
