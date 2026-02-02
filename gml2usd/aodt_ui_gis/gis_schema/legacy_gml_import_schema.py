# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

legacy_gml_import_schema = [
    ["in_gmls", str, ""],
    ["output_stage", str, "-o"],
    ["epsg_in", str, "--epsg_in"],
    ["epsg_out", str, "--epsg_out"],
    ["flatten", bool, "--flatten"],
    ["scale", float, "--scaling"],
    ["mobility_scale", float, " --mobility_scale"],
    ["max_lod", int, "--max_lod"],
    ["adjust_height_threshold", float, "--adjust_height_threshold"],
    ["textures", str, "--textures"],
    ["textures_out_dir", str, "--texture_out_prefix"],
    ["force_mobility", bool, "--force_mobility"],
    ["disable_mobility", bool, "--disable_mobility"]
]

