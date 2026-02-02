#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""USD -> glTF/GLB conversion helpers.

This is intended to run inside the gml2usd Docker image, where `pxr` is available.
We add `usd2gltf` via requirements.txt.

Notes:
- GLB is a single binary file, convenient for HTTP response.
- glTF (.gltf) is usually multiple files (.gltf + .bin + textures). For API usage,
  we package the whole output folder into a .zip.
"""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
import json
import shutil
import time

from pxr import Usd
from usd2gltf import converter

logger = logging.getLogger(__name__)


DEFAULT_REMOVE_PRIM_PATHS = [
    "/World/mobility_domain",
    "/World/ground_plane",
]


def _normalize_gltf_bin_names(output_dir: Path, *, base_name: str) -> None:
    """Rename the generated .bin to <base_name>.bin and update the .gltf buffer URI.

    This improves UX for API downloads (stable names like Askey.gltf/Askey.bin).
    Only applies when there is exactly one buffer URI ending with '.bin'.
    """
    gltf_path = output_dir / f"{base_name}.gltf"
    if not gltf_path.exists():
        return

    try:
        data = json.loads(gltf_path.read_text(encoding="utf-8"))
    except Exception:
        return

    buffers = data.get("buffers")
    if not isinstance(buffers, list) or len(buffers) != 1:
        return

    uri = buffers[0].get("uri") if isinstance(buffers[0], dict) else None
    if not isinstance(uri, str) or not uri.lower().endswith(".bin"):
        return

    old_bin = output_dir / uri
    if not old_bin.exists():
        return

    new_uri = f"{base_name}.bin"
    new_bin = output_dir / new_uri
    if new_bin.exists():
        # If a previous run left files around, keep the existing naming.
        return

    old_bin.rename(new_bin)
    buffers[0]["uri"] = new_uri

    gltf_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_prims(stage: Usd.Stage, remove_paths: list[str]) -> None:
    for prim_path in remove_paths:
        prim = stage.GetPrimAtPath(prim_path)
        if prim and prim.IsValid():
            stage.RemovePrim(prim_path)


def _open_stage_for_conversion(
    input_usd: Path,
    *,
    remove_prim_paths: list[str] | None,
) -> tuple[Usd.Stage, Path | None]:
    """Open a stage for conversion.

    If we need to remove prims, operate on a temporary copy to avoid mutating
    the original USD on disk.

    Returns (stage, temp_path_to_cleanup).
    """
    remove_paths = list(remove_prim_paths) if remove_prim_paths is not None else list(DEFAULT_REMOVE_PRIM_PATHS)
    if not remove_paths:
        stage = Usd.Stage.Open(str(input_usd))
        if stage is None:
            raise RuntimeError(f"Failed to open USD stage: {input_usd}")
        return stage, None

    temp_path = input_usd.with_name(f"{input_usd.stem}.tmp_{int(time.time() * 1000)}{input_usd.suffix}")
    shutil.copy2(str(input_usd), str(temp_path))

    stage = Usd.Stage.Open(str(temp_path))
    if stage is None:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise RuntimeError(f"Failed to open USD stage: {temp_path}")

    _remove_prims(stage, remove_paths)
    stage.GetRootLayer().Save()
    return stage, temp_path


def usd_to_glb(
    input_usd: str,
    output_glb: str,
    *,
    remove_prim_paths: list[str] | None = None,
) -> str:
    """Convert a USD file to a single .glb file.

    Returns the output path.
    """
    input_path = Path(input_usd)
    output_path = Path(output_glb)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stage, temp_path = _open_stage_for_conversion(input_path, remove_prim_paths=remove_prim_paths)

    factory = converter.Converter()
    factory.interpolation = "LINEAR"
    factory.flatten_xform_animation = False

    logger.info(f"usd2gltf: converting USD -> GLB: {input_path} -> {output_path}")
    factory.process(stage, str(output_path))

    if temp_path is not None:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
    return str(output_path)


def usd_to_gltf_dir(
    input_usd: str,
    output_dir: str,
    *,
    base_name: str | None = None,
    remove_prim_paths: list[str] | None = None,
) -> list[str]:
    """Convert USD -> glTF in a directory.

    Returns a list of generated file paths.
    """
    input_path = Path(input_usd)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    name = base_name or input_path.stem
    gltf_path = out_dir / f"{name}.gltf"

    stage, temp_path = _open_stage_for_conversion(input_path, remove_prim_paths=remove_prim_paths)

    factory = converter.Converter()
    factory.interpolation = "LINEAR"
    factory.flatten_xform_animation = False

    logger.info(f"usd2gltf: converting USD -> glTF: {input_path} -> {gltf_path}")
    factory.process(stage, str(gltf_path))

    if temp_path is not None:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass

    # Make the .bin name stable (<name>.bin) and update the .gltf to match.
    _normalize_gltf_bin_names(out_dir, base_name=name)

    generated = [str(p) for p in out_dir.iterdir() if p.is_file()]
    return generated


def usd_to_gltf_zip(
    input_usd: str,
    output_zip: str,
    *,
    base_name: str | None = None,
    remove_prim_paths: list[str] | None = None,
) -> str:
    """Convert USD -> glTF (.gltf + assets) and zip the outputs.

    Returns the output zip path.

    Implementation detail:
    - We ask usd2gltf to write a .gltf into a temp output directory.
    - Then we zip everything under that directory.
    """
    input_path = Path(input_usd)
    output_zip_path = Path(output_zip)
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)

    out_dir = output_zip_path.parent / (base_name or input_path.stem)
    generated_files = usd_to_gltf_dir(
        str(input_path),
        str(out_dir),
        base_name=(base_name or input_path.stem),
        remove_prim_paths=remove_prim_paths,
    )

    logger.info(f"Packing glTF outputs into zip: {output_zip_path}")
    with zipfile.ZipFile(str(output_zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in generated_files:
            p = Path(file_path)
            if p.is_file():
                zf.write(str(p), arcname=p.name)

    # Best-effort cleanup of the intermediate folder
    try:
        for file_path in generated_files:
            Path(file_path).unlink(missing_ok=True)
        out_dir.rmdir()
    except Exception:
        pass

    return str(output_zip_path)
