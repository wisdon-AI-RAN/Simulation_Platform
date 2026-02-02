# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

gml_import_schema = [
    ["in_gmls", str, ""],
    ["output_stage", str, "-o"],
    ["epsg_in", str, "--epsg_in"],
    ["epsg_out", str, "--epsg_out"],
    ["cm", bool, "--cm"],
    ["disable_interiors", bool, "--disable_interiors"],
    ["rough", bool, "--rough"]
]
