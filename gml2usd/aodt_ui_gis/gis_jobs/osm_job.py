# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import messages
import omni.client  # type: ignore
import omni.log  # type: ignore
import subprocess
import utils
from config import *
from argparse import ArgumentParser
import time
from gis_schema.osm_import_schema import osm_import_schema

def run_aodt_gis(in_usd, output_stage, self):

    cmd_str = f"python3 {aodt_usd2usd_location} {in_usd} -o {output_stage} --rough"

    for item in osm_import_schema:
        name = item[0]
        flag_type = item[1]
        aodt_flag = item[2]

        #if name in dir(self) and flag_type is not bool:
        #    print(name, self.__getattribute__(name))
        #    cmd_str = cmd_str + " " + aodt_flag + " " + str(self.__getattribute__(name))
        if name in dir(self) and flag_type is bool:
            if self.__getattribute__(name) == True:
                print(name, self.__getattribute__(name))
                cmd_str = cmd_str + " " + aodt_flag

    cmd_str = cmd_str

    #print(f"running command: {cmd_str}")
    subprocess.run(cmd_str, shell=True)


class OsmJob:
    def __init__(self):
        pass

    def set(self, is_connected=False, **kwargs):
        self.__dict__ = dict(kwargs)
        self._osm_process = None
        self._job_cancelled = False
        self._setting_texture_refs = False  # texture ref thread flag
        self._worker_update_interval = 3  # default is 3 seconds
        self.is_connected = is_connected

        if not os.path.exists(log_file_path):
            with open(log_file_path, 'w') as fp:
                pass   

    def run(self):
        start_time = time.time()

        if not self.is_connected:
            self._log_file_path = log_file_path

        cmd_str = utils.make_aodt_osm_command_str(self)

        if utils.bb_is_valid_and_acceptable(self, 100):

            # open log file for osm job logging
            with open(self._log_file_path, mode="wb") as f:
                # run osm job
                try:
                    self._osm_process = subprocess.Popen(cmd_str, shell=True, stdout=f)
                except Exception as e:
                    return (-1, f"Error running OSM job: {e}")

            # regularly poll job for updates
            prev_update = ""
            while self._osm_process.poll() is None and not self._job_cancelled:
                if int(time.time()) % self._worker_update_interval == 0:
                    # Sends the most recent update
                    curr_update = utils.getLastNLines(self._log_file_path, 1)
                    if len(curr_update) > 0:
                        if self.is_connected and prev_update != curr_update[0]:
                            self._send_gis_processing_update(curr_update[0])
                            prev_update = curr_update[0]
                time.sleep(1)

            self._osm_process.wait()
            
            in_usd = tmp_path
            output_stage= self.__getattribute__("output_stage")
            run_aodt_gis(in_usd, output_stage, self)
            


            print(output_stage)

            try:
                subprocess.call(f"rm -r {tmp_path}", shell=True)
            except:
                pass

            self._job_cancelled = False

            if self.is_connected:
                return (str(self._osm_process.returncode), "")
        else:
            print("error with bounding box.")

        endtime = time.time() - start_time
        print(f"Execution time: {round(endtime)} seconds.")

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
        else:
            pass


if __name__ == "__main__":

    parser = ArgumentParser(description="")

    parser.add_argument("-o", "--output_stage", type=str, required=True)
    parser.add_argument("-c", "--coords", nargs="*", type=float)
    parser.add_argument("-cint", "--disable_interiors", nargs="*", type=bool)

    args = parser.parse_args()

    coords = args.coords

    job_config = {
        "minLon": coords[0],
        "minLat": coords[1],
        "maxLon": coords[2],
        "maxLat": coords[3],
        "output_stage": args.output_stage,
        "disable_interiors": args.disable_interiors
    }

    osmjob = OsmJob()
    osmjob.set(**job_config)
    osmjob.run()

                            

