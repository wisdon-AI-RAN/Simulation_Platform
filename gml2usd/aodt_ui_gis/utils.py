import sys
sys.path.insert(1, '/src/aodt_gis/aodt_py/aodt_ui_gis')

from gis_schema.gml_import_schema import gml_import_schema
from gis_schema.legacy_gml_import_schema import legacy_gml_import_schema
from gis_schema.osm_import_schema import osm_import_schema
from config import *
import omni.client
import subprocess
import os
from pxr import Usd, UsdGeom, UsdShade, Vt
import numpy
from material_defaults import default_material_map
from area import area


def copy(src, dest):
    omni.client.copy_file(src, dest, behavior=omni.client.CopyBehavior.OVERWRITE)


def copy_dir(src, dest):
    omni.client.copy_folder(src, dest, behavior=omni.client.CopyBehavior.OVERWRITE)


def copy_tmp_template(template_location, tmp_path):
    subprocess.call(f"cp {template_location} {tmp_path}", shell=True)


def aodt_gis(cmd_str):
    #print(f"running command: {cmd_str}")
    subprocess.run(cmd_str, shell=True)

def make_legacy_aodt_gis_command_str(self):
    cmd_str = f"{aodt_legacy_gis_location}"
    for item in legacy_gml_import_schema:
        name = item[0]
        flag_type = item[1]
        aodt_flag = item[2]

        if name == "output_stage":
            cmd_str = cmd_str + " -o " + tmp_path
        elif name in dir(self) and flag_type is not bool:
            print(name, self.__getattribute__(name))
            cmd_str = cmd_str + " " + aodt_flag + " " + str(self.__getattribute__(name))
        elif name in dir(self) and flag_type is bool:
            print(name, self.__getattribute__(name))
            cmd_str = cmd_str + " " + aodt_flag

    cmd_str = cmd_str + " -v info"
    print(cmd_str)

    return cmd_str

def make_aodt_gis_indoor_command_str(self):
    cmd_str = f"python3 {aodt_gis_indoor_location}"
    for item in gml_import_schema:
        name = item[0]
        flag_type = item[1]
        aodt_flag = item[2]

        if name in dir(self) and flag_type is not bool:
            print(name, self.__getattribute__(name))
            cmd_str = cmd_str + " " + aodt_flag + " " + str(self.__getattribute__(name))
        elif name in dir(self) and flag_type is bool:
            if self.__getattribute__(name) == True:
                print(name, self.__getattribute__(name))
                cmd_str = cmd_str + " " + aodt_flag

    cmd_str = cmd_str
    print(cmd_str)

    return cmd_str

def make_aodt_gis_command_str(self):
    cmd_str = f"python3 {aodt_gis_location}"
    for item in gml_import_schema:
        name = item[0]
        flag_type = item[1]
        aodt_flag = item[2]

        if name in dir(self) and flag_type is not bool:
            print(name, self.__getattribute__(name))
            cmd_str = cmd_str + " " + aodt_flag + " " + str(self.__getattribute__(name))
        elif name in dir(self) and flag_type is bool:
            if self.__getattribute__(name) == True:
                print(name, self.__getattribute__(name))
                cmd_str = cmd_str + " " + aodt_flag

    cmd_str = cmd_str
    print(cmd_str)

    return cmd_str


def make_aodt_osm_command_str(self):

    cmd_str = f"python3 /src/aodt_gis/aodt_py/aodt_ui_gis/osm2usd.py -- "
    cmd_str += " -blo " + out_blend
    cmd_str += " -usd " + tmp_path
    cmd_str += " -c "
    for item in osm_import_schema:
        name = item[0]
        flag_type = item[1]
        

        if name in dir(self) and flag_type is not bool:
            if name == "output_stage":
                cmd_str += " -o " + str(self.__getattribute__(name))
            else:
                cmd_str += " " + str(self.__getattribute__(name))
       
    print(cmd_str)
    return cmd_str


def add_default_materials(usd):
    file = usd
    print("setting default materials...")
    stage = Usd.Stage.Open(str(file))

    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            vertices = UsdGeom.Mesh(prim).GetPointsAttr().Get()
            SurfaceTag = UsdGeom.PrimvarsAPI(prim).GetPrimvar("SurfaceTag")
            MaterialTag = UsdGeom.PrimvarsAPI(prim).GetPrimvar("MaterialTag")
            if SurfaceTag and MaterialTag:
                # change MaterialTag based on Defaults table
                try:
                    MaterialTag.Set(material_tag_from_surface_tag(SurfaceTag.Get()))
                except:
                    pass
    stage.GetRootLayer().Save()


def add_default_materials_to_stage(stage):
    print("setting default materials...")

    for prim in stage.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            vertices = UsdGeom.Mesh(prim).GetPointsAttr().Get()
            SurfaceTag = UsdGeom.PrimvarsAPI(prim).GetPrimvar("SurfaceTag")
            MaterialTag = UsdGeom.PrimvarsAPI(prim).GetPrimvar("MaterialTag")
            if SurfaceTag and MaterialTag:
                # change MaterialTag based on Defaults table
                try:
                    MaterialTag.Set(material_tag_from_surface_tag(SurfaceTag.Get()))
                except:
                    pass
    stage.GetRootLayer().Save()

def get_textures_dir(output_stage):
    base = os.path.dirname(output_stage)
    filename = os.path.basename(os.path.normpath(output_stage)).replace(".usd", "")
    texturesName = filename + "_textures"
    outputTexturesPath = os.path.join(base, texturesName)

    return outputTexturesPath


def get_textures_dir_name(output_stage):
    filename = os.path.basename(os.path.normpath(output_stage)).replace(".usd", "")
    texturesName = filename + "_textures"
    print(f"output stage: {output_stage}, textures name : {texturesName}")
    return texturesName


def update_texture_reference(stage, texture_dir_name):

    stage = stage

    path = f"./{texture_dir_name}"

    stage = Usd.Stage.Open(str(stage))

    for prim in stage.Traverse():

        if prim.IsA(UsdShade.Material):

            for child in prim.GetChildren():
                child_path = child.GetPath()

                shader = UsdShade.Shader(prim.GetPrimAtPath(child_path))

                current_path = shader.GetInput("file").Get()

                if "combined" in str(current_path) or "individual" in str(current_path):

                    png_name = os.path.basename(
                        os.path.normpath(str(current_path))
                    ).strip("@")

                    shader.GetInput("file").Set(os.path.join(path, png_name))

    stage.GetRootLayer().Save()


def convert_vt_to_np(array: Vt.IntArray) -> numpy.ndarray:
    return numpy.array(array)


def convert_np_to_vt(array: numpy.ndarray) -> Vt.IntArray:
    return Vt.IntArray.FromNumpy(array)


def material_tag_from_surface_tag(surface_tag):
    material_tag_np = convert_vt_to_np(surface_tag)

    for row in default_material_map:
        st_id = row[0]
        st_name = row[1]
        default_material = row[2]
        material_tag_np[material_tag_np == st_id] = default_material

    material_tag = convert_np_to_vt(material_tag_np)

    return material_tag


def bb_area(minLon, maxLon, minLat, maxLat):
    # obj = {'type':'Polygon','coordinates':[[[-180,-90],[-180,90],[180,90],[180,-90],[-180,-90]]]}
    obj = {
        "type": "Polygon",
        "coordinates": [
            [
                [minLon, minLat],
                [minLon, maxLat],
                [maxLon, maxLat],
                [maxLon, minLat],
                [minLon, minLat],
            ]
        ],
    }
    calc_area = area(obj)

    calc_area = calc_area / 1000000

    return calc_area


# validate bounding box
def valid_bb(minLon, maxLon, minLat, maxLat):

    print("validating bounding box")
    # check if lat/longs valid
    if (
        -90 <= minLat <= 90
        and -180 <= minLon <= 180
        and -90 <= maxLat <= 90
        and -180 <= maxLon <= 180
    ):
        print("bounding box is valid")
        return True
    else:
        print("bounding box is invalid")
        return False


def bb_size_acceptable(minLon, maxLon, minLat, maxLat, acceptable_km_sq):
    if bb_area(minLon, maxLon, minLat, maxLat) > acceptable_km_sq:
        print("This bounding box is too big. Try again with a smaller area.")
        exit()
        # return False
    else:
        print("bounding box is acceptable size")
        return True


def bb_is_valid_and_acceptable(self, acceptable_km_sq):

    minLon = self.__getattribute__("minLon")
    maxLon = self.__getattribute__("maxLon")
    minLat = self.__getattribute__("minLat")
    maxLat = self.__getattribute__("maxLat")

    if bb_size_acceptable(
        minLon, maxLon, minLat, maxLat, acceptable_km_sq
    ) and valid_bb(minLon, maxLon, minLat, maxLat):
        return True
    else:
        return False


def getLastNLines(fname, N):
    assert N >= 0
    pos = N + 1
    lines = []
    with open(fname) as f:
        while len(lines) <= N:
            try:
                f.seek(-pos, 2)
            except IOError:
                f.seek(0)
                break
            finally:
                lines = list(f)
            pos *= 2
    return lines[-N:]
