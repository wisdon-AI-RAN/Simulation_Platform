# Copilot instructions (Simulation Platform)

## Big picture
- This repo is a **2-service stack**:
  - `AODT-Agent/`: Flask API for remote AODT restart via SSH (`POST /restart`) and smoke test (`GET /test`).
  - `gml2usd/`: Flask API that generates CityGML and converts **GML/OBJ ➜ USD**, returning **USD as binary**.
- In **single-port mode**, Nginx routes paths to the right service (see `AODT-Agent/gateway/nginx.conf`).

## How to run (Docker)
- Preferred: single public port via gateway:
  - Prepare env files: `AODT-Agent/.env` and `gml2usd/.env` (examples: `AODT-Agent/.env.example`, `gml2usd/.env.example`).
  - Start from `AODT-Agent/`: `docker compose -f docker-compose.single-port.yml up -d --build`.
- AODT-Agent only: `docker compose up -d --build` in `AODT-Agent/` (port via `AODT_AGENT_PUBLIC_PORT`).

## Service boundaries & data flow
- `gml2usd/gml_api_ssh.py` is the API entrypoint (gunicorn in `gml2usd/Dockerfile`).
  - `/process_gml` runs `python3 Main.py` **non-interactively** by feeding stdin (Main.py is interactive), then calls `local_citygml2usd.convert_citygml_to_usd()`.
  - `convert_citygml_to_usd()` shells out to scripts under `/opt/aodt_ui_gis/` (mounted via Dockerfile `PYTHONPATH=/opt/aodt_gis_python:/opt/aodt_ui_gis`).
  - Endpoints return `send_file(BytesIO(...), mimetype='application/octet-stream')` and usually **delete temp files** afterwards.
- `AODT-Agent/controllers/restart_aodt.py` calls `utils/ssh_utils.execute_remote_script()` (Paramiko) using env vars.

## Project-specific conventions (important)
- If you add a new API route in single-port deployments, update **both**:
  - the Flask app (AODT-Agent or gml2usd)
  - the gateway routing in `AODT-Agent/gateway/nginx.conf`
- gml2usd is heavy/long-running:
  - Nginx timeouts/body size are tuned in `AODT-Agent/gateway/nginx.conf`.
  - gunicorn timeout is set in `gml2usd/Dockerfile`.
- Treat `gml2usd/local_pydeps/` and `gml2usd/aodt_ui_gis/` as **prebuilt/third-party** assets; avoid refactors there unless a change is required to fix integration.

## Quick API probes
- Gateway (single-port): `GET /health`, `GET /test`.
- Restart: `POST /restart` (requires valid SSH env in `AODT-Agent/.env`).
- Convert GML: `POST /to_usd` (multipart: `project_id`, `epsg_in`, `gml_file`, optional `epsg_out`).
