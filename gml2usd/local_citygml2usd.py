import os
import subprocess
from typing import Tuple
import logging


class ConversionError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def convert_citygml_to_usd(
    gml_path: str,
    usd_path: str,
    epsg_in: str = "3826",
    epsg_out: str = "32654",
    rough: bool = True,
    disable_interiors: bool = False,
    script_name: str = "citygml2aodt.py",
) -> Tuple[str, str]:
    """Convert a CityGML file to USD locally inside this container.

    Returns (stdout, stderr). Raises ConversionError on failure.
    """

    if not os.path.exists(gml_path):
        raise ConversionError(f"Input GML not found: {gml_path}")

    os.makedirs(os.path.dirname(usd_path) or ".", exist_ok=True)

    cmd = [
        "python3",
        f"/opt/aodt_ui_gis/{script_name}",
        gml_path,
        "--epsg_in",
        str(epsg_in),
        "--epsg_out",
        str(epsg_out),
        "-o",
        usd_path,
        "--cm",
    ]

    if rough:
        cmd.append("--rough")
    if disable_interiors:
        cmd.append("--disable_interiors")

    logger.info("Running converter: %s", " ".join(cmd))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        raise ConversionError(
            "citygml2aodt failed "
            f"(rc={proc.returncode})\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    if not os.path.exists(usd_path):
        raise ConversionError(
            f"USD not generated at expected path: {usd_path}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        )

    return stdout, stderr
