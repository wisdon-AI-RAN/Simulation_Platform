# Copilot instructions (Simulation Platform)

## Build / run commands (Docker)
### Single-port deployment (recommended)
```bash
# from repo root
cp gml2usd/.env.example gml2usd/.env
# optional: pin public port
cp .env.example .env

docker compose up -d --build
```

Useful ops:
```bash
docker compose ps
docker compose logs -f gateway
docker compose logs -f gml2usd
```

### Run gml2usd without gateway
```bash
cd gml2usd
docker build -t gml2usd:local .
mkdir -p gml_original_file processed_gmls processed_usds uploads logs

docker run --rm -p 5001:5001 \
  -v "$PWD/.env:/app/.env:ro" \
  -v "$PWD/gml_original_file:/app/gml_original_file:ro" \
  -v "$PWD/processed_gmls:/app/processed_gmls" \
  -v "$PWD/processed_usds:/app/processed_usds" \
  -v "$PWD/uploads:/app/uploads" \
  -v "$PWD/logs:/app/logs" \
  gml2usd:local
```

## High-level architecture
- **docker-compose** (default) runs two services:
  - `gateway` (nginx) exposes a single public port and reverse-proxies to `gml2usd:5001`.
  - `gml2usd` (Flask + gunicorn) does the heavy conversion work.
- **Gateway routing** lives in `Simulation_Agent/gateway/nginx.conf`:
  - `/health`, `/process_gml`, `/process_obj`, `/list_files` -> `gml2usd` upstream.
- **API entrypoint** is `gml2usd/gml_api_ssh.py` (started by gunicorn; see `gml2usd/Dockerfile`).
  - `POST /process_gml`:
    1) runs `python3 Main.py` by feeding stdin (Main.py is interactive) to generate `processed_gmls/<gml_name>`
    2) calls `local_citygml2usd.convert_citygml_to_usd()` which shells out to `python3 /opt/aodt_ui_gis/<script_name> ...` to generate USD
    3) returns **binary** output (default: bundle zip containing `.usd` + generated glTF assets)
  - `POST /process_obj`:
    1) saves upload to `uploads/`
    2) (optionally) validates OBJ has required object/group names
    3) converts OBJ -> CityGML via `obj_converter.py` (uses `pyproj` to place model at provided lat/lon)
    4) converts GML -> USD via the same `local_citygml2usd` pipeline
    5) returns **binary** output
- The converter scripts + native deps are shipped into the container under:
  - `/opt/aodt_ui_gis/` (scripts)
  - `/opt/aodt_gis_python/` + `/opt/aodt_gis_lib/` (prebuilt python/native libraries)

`AODT-Agent` has been split out as a separate service/repo and is not part of the default compose.

For same-machine development, you can optionally start it via `docker-compose.dev.yml`:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Key conventions (repo-specific)
- **Route changes must be reflected in two places** for single-port deployments:
  - Flask routes in `gml2usd/gml_api_ssh.py`
  - Nginx routes in `Simulation_Agent/gateway/nginx.conf`
- **Long-running conversions are expected**:
  - gunicorn uses `--timeout 600` (see `gml2usd/Dockerfile`)
  - nginx proxy timeouts/body size are tuned in `Simulation_Agent/gateway/nginx.conf`
- **Treat as vendored assets** (avoid refactors unless integration is broken):
  - `gml2usd/local_pydeps/`
  - `gml2usd/aodt_ui_gis/`
- **Output behavior (important for clients):**
  - default response for `/process_gml` and `/process_obj` is a **bundle zip** (`.usd` + glTF assets)
  - `output` can request: `usd`, `gml` (OBJ pipeline only), `gltf` (single-file), `gltf_zip`, `glb`
  - `keep_files` controls whether server-side temps under `processed_gmls/`, `processed_usds/` are deleted after responding
- **OBJ validation defaults** (in `/process_obj`): if the caller doesn’t specify `required_objects`/`required_object` and doesn’t set `skip_obj_validation=1`, the service requires `floor` and `roof` object/group names.
- **Large datasets / volumes**:
  - `gml2usd/gml_original_file/` is expected to be mounted read-only and can be very large
  - `processed_gmls/`, `processed_usds/`, `uploads/`, `logs/` are runtime outputs and are usually volume-mounted

## Quick API smoke checks
```bash
# Single-port gateway (default)
BASE_URL=http://localhost:8082
curl -sS "$BASE_URL/health" | cat

# /process_gml (default returns zip; use -o to write binary)
curl -f -sS -X POST "$BASE_URL/process_gml" \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"demo","lat":22.82539,"lon":120.40568,"margin":50,"epsg_in":"3826","epsg_out":"32654"}' \
  -o demo.zip

# /process_obj (default returns zip)
# curl -f -sS -X POST "$BASE_URL/process_obj" \
#   -F project_id=demo -F lat=22.82539 -F lon=120.40568 \
#   -F epsg_gml=3826 -F epsg_usd=32654 \
#   -F obj_file=@./your.obj \
#   -o demo.zip
```
