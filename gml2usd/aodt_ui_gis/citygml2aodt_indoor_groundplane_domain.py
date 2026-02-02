"""
Variant of `citygml2aodt_indoor.py`:

- Keeps the same CityGML -> USD conversion pipeline (buildings/terrain/etc.).
- **Changes mobility domain**: `/World/mobility_domain` is generated directly
  from the same geometry as `/World/ground_plane` (terrain mesh), instead of
  using building footprints / cutting logic.

This is useful when you want UE placement domain to match the ground plane.
"""

import numpy as np
import geometry_tools
import tessellation_tools
import pycitygml
import pyproj
import argparse
import pathlib
import os
import re
import aodt_usd
import utils

from pxr import Usd, UsdGeom, UsdShade, UsdLux, Sdf, Gf


def usd_safe_prim_name(raw_name: str) -> str:
    if raw_name is None:
        return "unnamed"
    raw_name = str(raw_name).strip()
    if not raw_name:
        return "unnamed"
    name = re.sub(r"[^A-Za-z0-9_]+", "_", raw_name)
    if not name:
        name = "unnamed"
    if name[0].isdigit():
        name = "_" + name
    return name


def make_unique_name(base: str, used: set) -> str:
    if base not in used:
        used.add(base)
        return base
    i = 1
    while f"{base}_{i}" in used:
        i += 1
    unique = f"{base}_{i}"
    used.add(unique)
    return unique


def add_attribute_if_not_present(prim, name, type, value, doc):
    if not prim.GetAttribute(name).IsValid():
        attr = prim.CreateAttribute(name, type)
        if value is not None:
            attr.Set(value)
        if doc is not None:
            attr.SetDocumentation(doc)
        return attr


def cleanup_simple(vertices, indices):
    lut = geometry_tools.collapseVertices(vertices)
    indices = lut[indices]

    # remove duplicate and degenerate triangles
    indices, tri_lut = geometry_tools.cleanupTriangleIndices(indices)

    # compact indices and remove unused vertices
    lut = geometry_tools.compactIndices(indices)
    out_vertices = vertices[lut]

    return out_vertices, indices


def combine_meshes(vertices, indices):
    offset = int(0)
    out_indices = []
    for v, i in zip(vertices, indices):
        out_indices.append(i + offset)
        offset += v.shape[0]
    return np.concatenate(vertices), np.concatenate(out_indices)


def extract_footprint(vertices, indices, z_threshold):
    out = []
    for i in range(0, len(indices), 3):
        triangle = vertices[indices[i : i + 3]]
        if np.all(triangle[:, 2] <= z_threshold):
            out.append(triangle)
    # Some GMLs don't contain any triangles near the lowest Z (e.g. open-bottom shells),
    # so footprint extraction can legitimately return nothing.
    if len(out) == 0:
        # Keep dtype/shape consistent with vertices: (0, 3)
        return vertices[:0]
    return np.concatenate(out, axis=0)


parser = argparse.ArgumentParser(
    prog="citygml2aodt_indoor_groundplane_domain",
    description="Import CityGML files into an AODT USD stage; mobility_domain is copied from ground_plane.",
)

parser.add_argument("files", nargs="+", type=pathlib.Path)
parser.add_argument(
    "--epsg_in",
    nargs="?",
    help="EPSG code of incoming CityGML data. Must be a geographic coordinate system (angular units).",
)
parser.add_argument(
    "--epsg_out",
    nargs="?",
    help="EPSG code of resulting USD stage. Must be a projected coordinate system (linear units). E.g., EPSG:32654 for UTM 54N.",
)
parser.add_argument("-o", "--output", default="a.usda", help="output file name")
parser.add_argument("-e", "--extra", action="store_false", help="add extra debug prims", default=False)
parser.add_argument("--navdump", action="store_true", help="dump raw navigation mesh")
parser.add_argument("--cm", action="store_true", help="output stage in cm", default=True)
parser.add_argument("--disable_interiors", action="store_true", help="disable procedural indoor")
parser.add_argument("--start", type=int, help="debug")
parser.add_argument("--stop", type=int, help="debug")
parser.add_argument("--rough", action="store_true", help="use rough (maybe more robust) outside mobility cutting")

args = parser.parse_args()

in_crs = pyproj.CRS.from_epsg(args.epsg_in)
out_crs = pyproj.CRS.from_epsg(args.epsg_out)
transform = pyproj.Transformer.from_crs(in_crs, out_crs)

lower = np.full(3, np.finfo(np.float64).max)
upper = np.full(3, np.finfo(np.float64).min)

terrain = dict()
buildings = dict()
footprints = []

for file in args.files:
    data = pycitygml.load_city_gml(file)
    for name, structure in data.items():
        vertices = structure["vertices"]
        indices = structure["indices"]

        # coordinate transform
        vertices[:, 0], vertices[:, 1], vertices[:, 2] = transform.transform(
            vertices[:, 0], vertices[:, 1], vertices[:, 2]
        )

        # clean up geometry: merge close vertices
        lut = geometry_tools.collapseVertices(vertices)
        indices = lut[indices]

        # remove duplicate and degenerate triangles
        indices, tri_lut = geometry_tools.cleanupTriangleIndices(indices)
        if "SurfaceTag" in structure:
            structure["SurfaceTag"] = structure["SurfaceTag"][tri_lut]

        # compact indices and remove unused vertices
        lut = geometry_tools.compactIndices(indices)
        vertices = vertices[lut]
        if "uv" in structure:
            structure["uv"] = structure["uv"][lut]
        if "texture_index" in structure:
            structure["texture_index"] = structure["texture_index"][lut]

        structure["vertices"] = vertices
        structure["indices"] = indices
        structure["lower"] = vertices.min(axis=0)
        structure["upper"] = vertices.max(axis=0)

        if structure["kind"] in (pycitygml.TINRelief, pycitygml.ReliefFeature):
            terrain[name] = structure
        else:
            lower = np.minimum(lower, structure["lower"])
            upper = np.maximum(upper, structure["upper"])
            buildings[name] = structure
            fp = extract_footprint(vertices, indices, structure["lower"][2] + 0.1)
            if fp.shape[0] > 0:
                footprints.append(fp)

center = 0.5 * (lower + upper)
center[2] = 0

if args.start is not None and args.stop is not None:
    footprints = footprints[args.start : args.stop]

# If we couldn't extract any footprint triangles (common for some datasets),
# fall back to a simple rectangle footprint from the overall building bbox.
if len(footprints) == 0:
    z = lower[2] if np.isfinite(lower[2]) else 0.0
    x0, y0 = float(lower[0]), float(lower[1])
    x1, y1 = float(upper[0]), float(upper[1])
    footprint_vertices = np.array(
        [
            [x0, y0, z],
            [x1, y0, z],
            [x1, y1, z],
            [x0, y0, z],
            [x1, y1, z],
            [x0, y1, z],
        ],
        dtype=np.float64,
    )
    print("[Footprint] warning: no footprint triangles found; using bbox rectangle fallback.")
else:
    footprint_vertices = np.concatenate(footprints, axis=0)
footprint_indices = np.arange(0, footprint_vertices.shape[0], dtype=np.uint32)
footprint_vertices -= center
footprint_vertices[:, 2] = 0
footprint_vertices, footprint_indices = cleanup_simple(footprint_vertices, footprint_indices)

stage = Usd.Stage.CreateNew(args.output)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
scaler = 1
if args.cm:
    UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.LinearUnits.centimeters)
    scaler = 100
else:
    UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.LinearUnits.meters)

usd_world = UsdGeom.Xform.Define(stage, "/World")
usd_world.AddTranslateOp().Set(value=(0, 0, 0))
usd_world.AddRotateXYZOp().Set(Gf.Vec3d(0, 0, 0))
usd_world.AddScaleOp().Set((1, 1, 1))

usd_buildings = UsdGeom.Xform.Define(stage, "/World/buildings")
add_attribute_if_not_present(usd_buildings.GetPrim(), "ObjectType", Sdf.ValueTypeNames.String, "building", "")
add_attribute_if_not_present(usd_buildings.GetPrim(), "AerialRFDiffraction", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(usd_buildings.GetPrim(), "AerialRFDiffusion", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(usd_buildings.GetPrim(), "AerialRFMesh", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(usd_buildings.GetPrim(), "AerialRFTransmission", Sdf.ValueTypeNames.Bool, False, "")

usd_buildings_exterior = UsdGeom.Xform.Define(stage, "/World/buildings/exterior")
add_attribute_if_not_present(
    usd_buildings_exterior.GetPrim(), "ObjectType", Sdf.ValueTypeNames.String, "building", ""
)
add_attribute_if_not_present(usd_buildings_exterior.GetPrim(), "AerialRFDiffraction", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(usd_buildings_exterior.GetPrim(), "AerialRFDiffusion", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(usd_buildings_exterior.GetPrim(), "AerialRFMesh", Sdf.ValueTypeNames.Bool, True, "")
add_attribute_if_not_present(
    usd_buildings_exterior.GetPrim(), "AerialRFTransmission", Sdf.ValueTypeNames.Bool, False, ""
)

if not args.disable_interiors:
    usd_buildings_interior = UsdGeom.Xform.Define(stage, "/World/buildings/interior")
    add_attribute_if_not_present(
        usd_buildings_interior.GetPrim(), "ObjectType", Sdf.ValueTypeNames.String, "buildingInterior", ""
    )
    add_attribute_if_not_present(usd_buildings_interior.GetPrim(), "AerialRFDiffraction", Sdf.ValueTypeNames.Bool, True, "")
    add_attribute_if_not_present(usd_buildings_interior.GetPrim(), "AerialRFDiffusion", Sdf.ValueTypeNames.Bool, True, "")
    add_attribute_if_not_present(usd_buildings_interior.GetPrim(), "AerialRFMesh", Sdf.ValueTypeNames.Bool, True, "")
    add_attribute_if_not_present(
        usd_buildings_interior.GetPrim(), "AerialRFTransmission", Sdf.ValueTypeNames.Bool, False, ""
    )

mtl_path = Sdf.Path("/Looks/PreviewSurface")
mtl = UsdShade.Material.Define(stage, mtl_path)
shader = UsdShade.Shader.Define(stage, mtl_path.AppendPath("Shader"))
shader.CreateIdAttr("UsdPreviewSurface")
shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.4, 0.4, 0.4))
mtl.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

all_nav_vertices = []
all_nav_indices = []
all_nav_type = []

used_building_names = set()

# When there is no terrain mesh, rebasing each building by its own min-Z will
# incorrectly flatten objects that are entirely above ground (e.g., roofs) onto z=0.
# Use one global offset instead.
global_z_offset = 0.0
if not terrain:
    global_z_offset = float(lower[2]) if np.isfinite(lower[2]) else 0.0

# Buildings (exterior + optional interior meshes)
for name, structure in buildings.items():
    raw_building_name = None
    if isinstance(structure.get("attributes"), dict):
        raw_building_name = structure["attributes"].get("gml:name")
    prim_name = make_unique_name(usd_safe_prim_name(raw_building_name or name), used_building_names)

    structure["vertices"] -= center
    structure["lower"] -= center
    structure["upper"] -= center

    if not terrain:
        structure["vertices"][:, 2] -= global_z_offset
        structure["lower"][2] -= global_z_offset
        structure["upper"][2] -= global_z_offset

    vertices = structure["vertices"]
    indices = structure["indices"]

    slices = np.arange(structure["lower"][2] + 0.1, structure["upper"][2] - 2, 3)
    vertices, indices, rings, parent = tessellation_tools.z_slice_mesh(vertices, indices, slices)

    clean_vertices, clean_indices = vertices, indices
    sliced = UsdGeom.Mesh.Define(stage, "/World/buildings/exterior/" + prim_name)
    sliced.GetPointsAttr().Set(scaler * clean_vertices)
    sliced.GetFaceVertexCountsAttr().Set(np.full(len(clean_indices) // 3, 3))
    sliced.GetFaceVertexIndicesAttr().Set(clean_indices)

    tags = None
    if "SurfaceTag" in structure:
        tags = structure["SurfaceTag"][parent]
    aodt_usd.set_aodt_properties(
        sliced, rf_mesh=True, diffuse=True, diffraction=True, transmission=False, object_type="building"
    )
    aodt_usd.add_aodt_material_arrays(sliced, tags)

    # Interior navigation mesh (optional)
    if len(slices) != 0 and not args.disable_interiors:
        p, e1, e2 = tessellation_tools.building_orientation(vertices, rings)
        grid_vertices, grid_indices = tessellation_tools.generate_grid_stack(slices, p, e1, e2)
        cuts = rings + grid_vertices.shape[0]
        grid_vertices = np.concatenate((grid_vertices, vertices))
        grid_vertices, outside, inside = tessellation_tools.cutLines(grid_vertices, grid_indices, cuts)
        inside_vertices, inside_indices = cleanup_simple(grid_vertices, inside)

        check_lower = (inside_vertices[:, 0:2] > np.array([structure["lower"][0:2]]) - 0.5).all()
        check_upper = (inside_vertices[:, 0:2] < np.array([structure["upper"][0:2]]) + 0.5).all()
        if args.extra:
            if not check_lower or not check_upper:
                print("interior generation failed for " + name)
                continue

        inside_indices = tessellation_tools.add_staircase(inside_vertices, inside_indices, slices)
        all_nav_vertices.append(inside_vertices)
        all_nav_indices.append(inside_indices)
        all_nav_type.append(np.full(len(inside_indices) // 3, 1, dtype=np.int32))

        stacked = UsdGeom.Mesh.Define(stage, "/World/buildings/interior/" + prim_name)
        stacked.GetPointsAttr().Set(scaler * inside_vertices)
        stacked.GetFaceVertexCountsAttr().Set(np.full(len(inside_indices) // 3, 3))
        stacked.GetFaceVertexIndicesAttr().Set(inside_indices)
        aodt_usd.set_aodt_properties(
            stacked, rf_mesh=True, diffuse=False, diffraction=False, transmission=False, object_type="buildingInterior"
        )
        aodt_usd.add_aodt_material_arrays(stacked, None)

# Terrain -> ground_plane (also used for mobility_domain in this variant)
nav_vertices = []
nav_indices = []

for name, structure in terrain.items():
    structure["vertices"] -= center
    structure["lower"] -= center
    structure["upper"] -= center

    vertices = structure["vertices"]
    indices = structure["indices"]

    if args.extra:
        obj = UsdGeom.Mesh.Define(stage, "/World/" + name.replace("-", "_"))
        obj.GetPointsAttr().Set(scaler * vertices)
        obj.GetFaceVertexCountsAttr().Set(np.full(len(indices) // 3, 3))
        obj.GetFaceVertexIndicesAttr().Set(indices)
        UsdShade.MaterialBindingAPI.Apply(obj.GetPrim())
        UsdShade.MaterialBindingAPI(obj).Bind(mtl)

    clip_planes = np.array(
        [
            [1, 0, 0, upper[0] - center[0] + 100],
            [-1, 0, 0, -lower[0] + center[0] + 100],
            [0, 1, 0, upper[1] - center[1] + 100],
            [0, -1, 0, -lower[1] + center[1] + 100],
        ],
        np.float64,
    )

    vertices, indices = tessellation_tools.clipMesh(vertices, indices, clip_planes)
    vertices, indices = cleanup_simple(vertices, indices)
    nav_vertices.append(vertices)
    nav_indices.append(indices)

if not nav_vertices:
    nav_vertices.append(
        np.array(
            [
                [upper[0] - center[0] + 10, upper[1] - center[1] + 10, 0],
                [lower[0] - center[0] - 10, upper[1] - center[1] + 10, 0],
                [lower[0] - center[0] - 10, lower[1] - center[1] - 10, 0],
                [upper[0] - center[0] + 10, lower[1] - center[1] - 10, 0],
            ],
            np.float64,
        )
    )
    nav_indices.append(np.array([0, 1, 2, 0, 2, 3], np.uint32))

terrain_vertices, terrain_indices = combine_meshes(nav_vertices, nav_indices)
terrain_vertices, terrain_indices = cleanup_simple(terrain_vertices, terrain_indices)

print("tessellate")
_nav_vertices_tess, _nav_indices_tess = tessellation_tools.tessellateMesh(terrain_vertices, terrain_indices, 4.0)

print("build mobility domain FROM ground_plane")

# IMPORTANT CHANGE: mobility_domain copies ground_plane triangles.
# Ignore any previously accumulated interior nav meshes.
all_nav_vertices = [terrain_vertices]
all_nav_indices = [terrain_indices]
all_nav_type = [np.full(len(terrain_indices) // 3, 0, dtype=np.int32)]

mobility_vertices, mobility_indices = combine_meshes(all_nav_vertices, all_nav_indices)
mobility_type = np.concatenate(all_nav_type)

print("output")

usd_terrain = UsdGeom.Mesh.Define(stage, "/World/ground_plane")
usd_terrain.GetPointsAttr().Set(scaler * terrain_vertices)
usd_terrain.GetFaceVertexCountsAttr().Set(np.full(len(terrain_indices) // 3, 3))
usd_terrain.GetFaceVertexIndicesAttr().Set(terrain_indices)
aodt_usd.set_aodt_properties(
    usd_terrain, rf_mesh=True, diffuse=False, diffraction=False, transmission=False, object_type="terrain"
)
aodt_usd.add_aodt_material_arrays(usd_terrain, None)

usd_navigation = UsdGeom.Mesh.Define(stage, "/World/mobility_domain")
usd_navigation.GetPointsAttr().Set(scaler * mobility_vertices)
usd_navigation.GetFaceVertexCountsAttr().Set(np.full(len(mobility_indices) // 3, 3))
usd_navigation.GetFaceVertexIndicesAttr().Set(mobility_indices)
UsdGeom.PrimvarsAPI(usd_navigation).CreatePrimvar(
    "MobilityType", Sdf.ValueTypeNames.IntArray, UsdGeom.Tokens.uniform
).Set(mobility_type)

if args.navdump:
    mobility_vertices.astype(np.float32).tofile("vertices.bin")
    mobility_indices.astype(np.uint32).tofile("indices.bin")

if args.extra:
    usd_footprints = UsdGeom.Mesh.Define(stage, "/World/building_footprints")
    usd_footprints.GetPointsAttr().Set(scaler * footprint_vertices)
    usd_footprints.GetFaceVertexCountsAttr().Set(np.full(len(footprint_indices) // 3, 3))
    usd_footprints.GetFaceVertexIndicesAttr().Set(footprint_indices)

scenario = aodt_usd.write_scenario_info(stage)
stage.SetDefaultPrim(scenario.GetPrim())

stage.DefinePrim("/Materials", "Scope")
standard = stage.DefinePrim("/Materials/standard")
materials_ref = "../assets/materials.usda"
materials_abs = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(args.output)), materials_ref))
if os.path.exists(materials_abs):
    standard.GetReferences().AddReference(materials_ref)
else:
    print(f"[Materials] warning: missing materials.usda at {materials_abs}; skipping reference.")

stage.DefinePrim("/UEs", "Scope")
stage.DefinePrim("/RUs", "Scope")
stage.DefinePrim("/Panels", "Scope")
stage.DefinePrim("/DUs", "Scope")

light_prim = stage.DefinePrim("/dome_light", "DomeLight")
light = UsdLux.DomeLight(light_prim)
light.GetIntensityAttr().Set(1000)

utils.add_default_materials_to_stage(stage)
stage.GetRootLayer().Save()


