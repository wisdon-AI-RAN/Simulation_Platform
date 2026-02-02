# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import os

# paths for asim assets (template, aodt_gis executable)
# and scratch folder
drive = "/src/aodt_gis/data"  # assumed mounted drive
template_location = "/src/aodt_gis/template/template.usd"
tmp_path = os.path.join(drive, "tmp.usd")
tmp_textures_path = os.path.join(drive, "tmp_textures")
aodt_gis_location = "/src/aodt_gis/aodt_py/aodt_ui_gis/citygml2aodt.py"
aodt_gis_indoor_location = "/src/aodt_gis/aodt_py/aodt_ui_gis/citygml2aodt_indoor.py"
aodt_legacy_gis_location = "/src/aodt_gis/build/aodt_gis"
aodt_usd2usd_location = "/src/aodt_gis/aodt_py/aodt_ui_gis/usd2usd.py"
tmp_path2 = os.path.join(drive, "tmp2.usd")
tmp_textures_path2 = os.path.join(drive, "tmp2_textures")
out_blend = os.path.join(drive, 'tmp.blend')
log_file_path = "/src/aodt_gis/data/tmp_log.txt"
