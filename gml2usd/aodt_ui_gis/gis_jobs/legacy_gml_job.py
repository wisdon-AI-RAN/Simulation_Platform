# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import sys
sys.path.insert(1, '/src/aodt_gis/aodt_py/aodt_ui_gis')

import asyncio
#import utils
import utils as utils
import subprocess
from config import *
import messages as messages
import omni.client  # type: ignore
import omni.log  # type: ignore
import os
import threading
import multiprocessing
import time
from argparse import ArgumentParser
import time


class GmlJob:
    def __init__(self):
        pass

    def set(self, is_connected=False, **kwargs):
        self.__dict__ = dict(kwargs)
        self._gml_process = None
        self._job_cancelled = False
        self.is_connected = is_connected

        if not os.path.exists(log_file_path):
            with open(log_file_path, 'w') as fp:
                pass

    def run(self):

        if not self.is_connected:
            self._log_file_path = log_file_path

        # preliminary clean up
        start_time = time.time()

        if os.path.exists(tmp_path):
            subprocess.call(f"rm -r {tmp_path}", shell=True)
        else:
            pass
        if os.path.exists(tmp_textures_path):
            subprocess.call(f"rm -r {tmp_textures_path}", shell=True)
        else:
            pass

        # copy template
        utils.copy_tmp_template(template_location, tmp_path)

        gml_list = self.in_gmls.split(" ")
        # validate input files
        for file in gml_list:
            if not os.path.exists(file):
                print(f"{file} path not exists")
                return (-1, f"File not found: {file}")

        # create gml job command string
        # validate input files
        for file in self.in_gmls.split(" "):
            if not os.path.exists(file):
                return (-1, f"File not found: {file}")

        # create gml job command string
        cmd_str = utils.make_legacy_aodt_gis_command_str(self)
        #print(f"running command: {cmd_str}")

        # open log file for gml job logging
        with open(self._log_file_path, mode="wb") as f:
            # run gml job
            try:
                self._gml_process = subprocess.Popen(cmd_str, shell=True, stdout=f)
            except Exception as e:
                return (-1, f"Error running GML Job: {e}")

        if self.is_connected:
            # regularly poll job for updates
            prev_update = ""
            while self._gml_process.poll() is None and not self._job_cancelled:
                if int(time.time()) % self._worker_update_interval == 0:
                    # Sends the most recent update
                    curr_update = utils.getLastNLines(self._log_file_path, 1)
                    if len(curr_update) > 0:
                        if self.is_connected and prev_update != curr_update[0]:
                            self._send_gis_processing_update(curr_update[0])
                            prev_update = curr_update[0]
                time.sleep(1)

        self._gml_process.wait()

        # set texture refs
        if not self._job_cancelled and self._gml_process.returncode == 0:
            try:
                utils.add_default_materials(tmp_path)
            except:
                print("default materials not set")
                return (-1, f"Error setting textures: {e}")

            try:
                self._send_gis_processing_update("copying textures directory...")

                utils.copy_dir(
                    tmp_textures_path, utils.get_textures_dir(self.output_stage)
                )

            except:
                print("could not copy textures file")
                return (-1, f"Error setting textures: {e}")

            utils.copy(tmp_path, self.output_stage)

            # set texture dirs
            try:

                self._send_gis_processing_update("updating texture references...")

                textures_dir_name = utils.get_textures_dir_name(self.output_stage)

                utils.update_texture_reference(self.output_stage, textures_dir_name)

            except Exception as e:
                print(f"error setting texture directory link: {e}")
                return (-1, f"Error setting textures: {e}")

        # clean up
        try:
            subprocess.call(f"rm -r {tmp_path}", shell=True)
        except:
            pass
        try:
            subprocess.call(f"rm -r {tmp_textures_path}", shell=True)
        except:
            pass

        # reset cancel flag
        self._job_cancelled = False

        endtime = time.time() - start_time
        print(f"Execution time: {round(endtime)} seconds.")

        # return job success or failure
        if self.is_connected:
            return (self._gml_process.returncode, "")

    def end_job(self):
        self._job_cancelled = True
        self._gml_process.terminate()

    ### Messaging ###

    def _send_message(self, channel, message: messages.WorkerMessage):
        if channel is None:
            omni.log.error("Cannot send message as Channel is None.")
            return

        omni.client.send_message(channel.id, message.get_as_json().encode())

    def _send_gis_processing_update(self, line):
        print(line)
        if self.is_connected:
            gis_processing_update_payload = messages.gis_update_payload
            gis_processing_update_payload["status"] = "gis_processing_update"
            gis_processing_update_payload["stdout"] = line
            self._send_message(
                channel=self._worker_channel_handler,
                message=messages.GisStatusUpdate(
                    from_name=self._uuid,
                    to_name=self._recv_uuid,
                    _gis_update_payload=gis_processing_update_payload,
                ),
            )


if __name__ == "__main__":

    parser = ArgumentParser(description="")

    parser.add_argument(
        "-i", "--in_gmls", nargs="*", type=lambda s: [i for i in s.split(",")]
    )
    parser.add_argument("-o", "--output", type=str, required=True)
    parser.add_argument("-ei", "--epsg_in", type=str)
    parser.add_argument("-eo", "--epsg_out", type=str)
    parser.add_argument("-f", "--flatten", type=bool)
    parser.add_argument("-s", "--scaling", type=float)
    parser.add_argument("-mobility_scale", "--mobility_scale", type=float)
    parser.add_argument("-max_lod", "--max_lod", type=int)
    parser.add_argument(
        "-adjust_height_threshold", "--adjust_height_threshold", type=float
    )
    parser.add_argument("-textures", "--textures", type=bool)
    parser.add_argument("-textures_out_dir", "--textures_out_dir", type=str)
    parser.add_argument("-force_mobility", "--force_mobility", type=bool)
    parser.add_argument("-disable_mobility", "--disable_mobility", type=bool)

    args = parser.parse_args()

    gmls = ""
    for gml in args.in_gmls:
        gmls = gmls + gml[0].strip(" ") + " "
    gmls = gmls[:-1]

    job_params = {
        "in_gmls": gmls,
        "output_stage": args.output,
        "epsg_in": args.epsg_in,
        "epsg_out": args.epsg_out,
        "flatten": args.flatten,
        "scale": args.scaling,
        "mobility_scale": args.mobility_scale,
        "max_lod": args.max_lod,
        "adjust_height_threshold": args.adjust_height_threshold,
        "textures": args.textures,
        "textures_out_dir": args.textures_out_dir,
        "disable_mobility": args.disable_mobility,
        "force_mobility": args.force_mobility,
    }

    keys = []
    for key, value in job_params.items():
        if value is None:
            keys.append(key)
    for key in keys:
        del job_params[key]

    job = GmlJob()
    job.set(**job_params)
    job.run()
