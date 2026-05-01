# Build from Source (Without Docker)

This guide explains how to set up Open Library for local development without Docker. It covers installing dependencies, building frontend assets, and running the web server natively.

> **Note:** Open Library depends on external services (Solr, PostgreSQL, Infobase). The easiest approach for most developers is to run those services via Docker while running the Python web server natively. This guide covers that hybrid setup, as well as a fully native path for advanced contributors.

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.12 | [python.org/downloads](https://www.python.org/downloads/) |
| Node.js | 24 | [nodejs.org](https://nodejs.org/) — use `^24.0.0` |
| npm | bundled with Node | comes with Node.js |
| Git | any recent | required for submodules |

Verify your versions before continuing:

```sh
python3 --version   # should be 3.12.x
node --version      # should be v24.x.x
npm --version
git --version
```

## 1. Clone the Repository

```sh
git clone https://github.com/internetarchive/openlibrary.git
cd openlibrary
```

## 2. Initialize Git Submodules

Open Library uses `vendor/infogami` as a git submodule. Initialize it before installing Python dependencies:

```sh
git submodule init
git submodule sync
git submodule update
```

Or equivalently via Make:

```sh
make git
```

## 3. Install Python Dependencies

Using `pip` with a virtual environment:

```sh
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Alternatively, if you have [`uv`](https://github.com/astral-sh/uv) installed (used in the Docker image):

```sh
uv pip install -r requirements.txt
```

To also install test dependencies:

```sh
pip install -r requirements_test.txt
```

## 4. Install Node.js Dependencies

```sh
npm install --no-audit
```

## 5. Build Frontend Assets

```sh
npm run build-assets
```

This compiles CSS, JavaScript, Vue components, and Lit components into `static/build/`. To rebuild only specific asset types:

```sh
npm run build-assets:css
npm run build-assets:js
npm run build-assets:components
npm run build-assets:lit-components
```

For active frontend development with live rebuilding:

```sh
npm run watch
```

## 6. Compile i18n Messages

```sh
python scripts/i18n-messages compile
```

## 7. Run the Web Server

### Option A: Hybrid setup (recommended)

Start the dependent services (Solr, PostgreSQL, Infobase) via Docker, then run the web server natively. This gives faster Python reload cycles without a full Docker rebuild.

```sh
# Start only the service dependencies
docker compose up -d db solr infobase

# Run the web server natively (in a separate terminal)
PYTHONPATH=./vendor/infogami:. python scripts/openlibrary-server conf/openlibrary.yml --bind :8080
```

Visit <http://localhost:8080>.

### Option B: Fully native

Advanced contributors who want to run all services natively will need to install and configure PostgreSQL and Solr separately. Refer to:

- [Solr setup](https://solr.apache.org/guide/solr/latest/getting-started/installing-solr.html) — use the schema in `solr/conf/`
- [PostgreSQL setup](https://www.postgresql.org/download/) — create a database named `openlibrary`

## 8. Run Tests

Unit and integration tests can be run natively without Docker:

```sh
pytest openlibrary/tests/
```

JavaScript tests:

```sh
npm run test:js
```

## Troubleshooting

### `No module named 'infogami'`

The `vendor/infogami` submodule was not initialized. Run:

```sh
git submodule init && git submodule sync && git submodule update
```

### `ModuleNotFoundError` for a package in `requirements.txt`

Make sure your virtual environment is activated before running the server:

```sh
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### Frontend assets missing or stale

Rebuild assets after pulling changes that touch JS/CSS:

```sh
npm run build-assets
```

### Port 8080 already in use

Change the bind port:

```sh
PYTHONPATH=./vendor/infogami:. python scripts/openlibrary-server conf/openlibrary.yml --bind :8081
```
