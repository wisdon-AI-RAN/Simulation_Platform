# Base: use Ubuntu 22.04 so we can install libicu70 (pycitygml depends on libicuuc.so.70)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System deps for USD/CityGML native extensions (headless) + Python runtime
RUN apt-get update \
		&& apt-get install -y --no-install-recommends \
			ca-certificates \
			libcurl3-gnutls \
			libpython3.10 \
			python3.10 \
			python3-pip \
			libglu1-mesa \
			libgl1 \
			libicu70 \
		&& rm -rf /var/lib/apt/lists/*

# Local USD/geometry python deps (prebuilt .so + pxr)
COPY local_pydeps/aodt_gis_python/ /opt/aodt_gis_python/

# Native shared libs required by the prebuilt python extensions (e.g. libcitygml.so.2)
COPY local_pydeps/aodt_gis_lib/ /opt/aodt_gis_lib/

# Official conversion scripts (citygml2aodt.py etc.)
COPY aodt_ui_gis/ /opt/aodt_ui_gis/

# gml_original_file is huge; keep it on the host and mount it into the container at runtime.
RUN mkdir -p /app/gml_original_file
#install pacakges
COPY requirements.txt /app/
RUN python3 -m pip install --no-cache-dir -r requirements.txt
RUN mkdir -p processed_gmls
RUN chmod 777 processed_gmls
RUN mkdir -p processed_usds
RUN chmod 777 processed_usds
#copy files
COPY gml_api_ssh.py /app/
COPY local_citygml2usd.py /app/
COPY obj_converter.py /app/
COPY usd_to_gltf.py /app/
COPY gml_bounding_boxes_v1.csv /app/
COPY Main.py /app/
COPY excluded_buildings.txt /app/
COPY gml_transport_v2.py /app/
COPY .env /app/

ENV PYTHONPATH=/opt/aodt_gis_python:/opt/aodt_ui_gis
ENV LD_LIBRARY_PATH=/opt/aodt_gis_lib

EXPOSE 5001

CMD ["gunicorn", "--workers", "4" , "--timeout","600","--bind","0.0.0.0:5001","gml_api_ssh:app"]