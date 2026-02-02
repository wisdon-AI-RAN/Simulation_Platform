import numpy as np
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Kind

def add_attribute_if_not_present(prim, name, type, value, doc):
  if not prim.GetAttribute(name).IsValid():
    attr = prim.CreateAttribute(name, type)
    if value is not None:
      attr.Set(value)
    if doc is not None:
      attr.SetDocumentation(doc)
    return attr

def write_scenario_info(stage):
  scenario = stage.GetPrimAtPath("/Scenario")
  if not scenario.IsValid():
    scenario = stage.DefinePrim("/Scenario", "Scenario")
    Usd.ModelAPI(scenario).SetKind(Kind.Tokens.component)

  add_attribute_if_not_present(scenario, "pathViz:enableTemperatureColor", Sdf.ValueTypeNames.Bool, True, "When enabled, the visualized paths are colored based on their power level, from red (strongest) to blue (weakest). Otherwise, they all have the same color.")
  add_attribute_if_not_present(scenario, "pathViz:maxDynamicRangeDB", Sdf.ValueTypeNames.UInt, 200, "Maximum power dynamic range (in dB) of the visualized paths.")
  add_attribute_if_not_present(scenario, "pathViz:maxNumPaths", Sdf.ValueTypeNames.UInt, 1000, "Maximum number of paths to be visualized within the specified power dynamic range.")
  add_attribute_if_not_present(scenario, "pathViz:raysSparsity", Sdf.ValueTypeNames.Int, 1, None)
  add_attribute_if_not_present(scenario, "pathViz:raysWidth", Sdf.ValueTypeNames.Float, 8, None)
  add_attribute_if_not_present(scenario, "sim:batches", Sdf.ValueTypeNames.Int, 1, None)
  add_attribute_if_not_present(scenario, "sim:duration", Sdf.ValueTypeNames.Float, 0, "Desired duration of the simulation.")
  add_attribute_if_not_present(scenario, "sim:em:diffuse_type", Sdf.ValueTypeNames.Int, 0, None)
  add_attribute_if_not_present(scenario, "sim:em:interactions", Sdf.ValueTypeNames.Int, 5, None)
  add_attribute_if_not_present(scenario, "sim:em:rays", Sdf.ValueTypeNames.Int, 500, None)
  add_attribute_if_not_present(scenario, "sim:em:sphere_radius", Sdf.ValueTypeNames.Float, 2, None)
  add_attribute_if_not_present(scenario, "sim:enable_training", Sdf.ValueTypeNames.Bool, None, None)
  add_attribute_if_not_present(scenario, "sim:enable_wideband", Sdf.ValueTypeNames.Bool, 1, "When enabled, wideband CFRs are computed.")
  add_attribute_if_not_present(scenario, "sim:gnb:panel_type", Sdf.ValueTypeNames.Token, "panel_02", "Panel for the gNB")
  add_attribute_if_not_present(scenario, "sim:interval", Sdf.ValueTypeNames.Float, 0, "Interval at which the radio environment is sampled. [s]")
  add_attribute_if_not_present(scenario, "sim:is_full", Sdf.ValueTypeNames.Bool, None, None)
  add_attribute_if_not_present(scenario, "sim:is_seeded", Sdf.ValueTypeNames.Bool, 0, None)
  add_attribute_if_not_present(scenario, "sim:ml_example", Sdf.ValueTypeNames.Int, None, None)
  add_attribute_if_not_present(scenario, "sim:mobility", Sdf.ValueTypeNames.UInt, 1, None)
  add_attribute_if_not_present(scenario, "sim:num_procedural_ues", Sdf.ValueTypeNames.UInt, 0, None)
  add_attribute_if_not_present(scenario, "sim:num_users", Sdf.ValueTypeNames.UInt, 0, "Number of users for the simulation.")
  add_attribute_if_not_present(scenario, "sim:pause", Sdf.ValueTypeNames.UInt, 0, None)
  add_attribute_if_not_present(scenario, "sim:play", Sdf.ValueTypeNames.UInt, 0, None)
  add_attribute_if_not_present(scenario, "sim:samples_per_slot", Sdf.ValueTypeNames.Int, 0, None)
  add_attribute_if_not_present(scenario, "sim:seed", Sdf.ValueTypeNames.UInt, None, None)
  add_attribute_if_not_present(scenario, "sim:slots_per_batch", Sdf.ValueTypeNames.Int, 0, None)
  add_attribute_if_not_present(scenario, "sim:stop", Sdf.ValueTypeNames.UInt, 1, None)
  add_attribute_if_not_present(scenario, "sim:ue:batch_drop_radius", Sdf.ValueTypeNames.Float, 10, None)
  add_attribute_if_not_present(scenario, "sim:ue:height", Sdf.ValueTypeNames.Float, 1.5, "Default UE height [m]")
  add_attribute_if_not_present(scenario, "sim:ue:panel_type", Sdf.ValueTypeNames.Token, "panel_01", "Panel for the UE")
  add_attribute_if_not_present(scenario, "sim:ueMaxSpeed", Sdf.ValueTypeNames.Float, 2.5, "Maximum speed to be considered for the UEs [m/s].")
  add_attribute_if_not_present(scenario, "sim:ueMinSpeed", Sdf.ValueTypeNames.Float, 1.5, "Minimum speed to be considered for the UEs [m/s].")

  return scenario

def set_aodt_properties(mesh, rf_mesh, diffuse, diffraction, transmission, object_type):
  mesh.GetPrim().CreateAttribute("AerialRFMesh", Sdf.ValueTypeNames.Bool).Set(rf_mesh)
  mesh.GetPrim().CreateAttribute("AerialRFDiffuse", Sdf.ValueTypeNames.Bool).Set(diffuse)
  mesh.GetPrim().CreateAttribute("AerialRFDiffraction", Sdf.ValueTypeNames.Bool).Set(diffraction)
  mesh.GetPrim().CreateAttribute("AerialRFTransmission", Sdf.ValueTypeNames.Bool).Set(transmission)
  mesh.GetPrim().CreateAttribute("ObjectType", Sdf.ValueTypeNames.String).Set(object_type)

def add_aodt_material_arrays(mesh, values):
  if values is None:
    surfacecount = len(mesh.GetFaceVertexCountsAttr().Get())
    values = np.full(surfacecount, 0)
  UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('SurfaceTag', Sdf.ValueTypeNames.IntArray, UsdGeom.Tokens.uniform).Set(values);
  UsdGeom.PrimvarsAPI(mesh).CreatePrimvar('MaterialTag', Sdf.ValueTypeNames.IntArray, UsdGeom.Tokens.uniform).Set(values);

