# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#


from gis_jobs.gml_job import GmlJob
from gis_jobs.osm_job import OsmJob
from gis_schema.gml_import_schema import gml_import_schema
from argparse import ArgumentParser
import json
import asyncio
import omni.client  # type: ignore
import omni.log  # type: ignore
import messages
import uuid
import time
from pathlib import Path
import datetime
import subprocess
import datetime

WORKER_CONNECTION_TIMEOUT = 60  # seconds
WORKER_UPDATE_INTERVAL = 2  # seconds
LOG_DIR_PATH = "/src/aodt_gis/data/logs/"


def get_channel_listener_instance():
    global _instance
    if _instance is None:
        _instance = ChannelListener()
    return _instance


class ChannelListener:
    def __init__(self, server_path, broadcast_channel_name):
        global _instance
        _instance = self

        # Setting server path and broadcast channel names
        self._server_path = server_path
        self._broadcast_channel_name = broadcast_channel_name

        # Initial general broadcast channel url and handler
        self._broadcast_channel_url = omni.client.combine_urls(
            self._server_path, self._broadcast_channel_name
        )
        self._broadcast_channel_handler = None

        # Initial worker channel url and handler
        self._worker_channel_url = None
        self._worker_channel_handler = None
        self._worker_prev_time = 0

        self._connection_status_sub = omni.client.register_connection_status_callback(
            self._connectionStatusCallback
        )
        self._logging_enabled = True

        self._uuid = str(uuid.uuid4())
        self._recv_uuid = None

        self._current_job = None
        self._job_in_progress = False
        self._job_cancelled = False

        self._heartbeat_update_process = None

        self._start_omniverse()

    ### Start Omniverse ###

    def _start_omniverse(self):
        omni.client.initialize()
        omni.client.set_retries(0, 0, 0)

        omni.log.get_log().level = (
            omni.log.Level.VERBOSE if self._logging_enabled else omni.log.Level.DEBUG
        )

    def _connectionStatusCallback(self, url, status):
        if status not in (
            omni.client.ConnectionStatus.CONNECTING,
            omni.client.ConnectionStatus.CONNECTED,
        ):
            omni.log.fatal(
                f"Error connecting to Nucleus URL: <{url}> (OmniClientConnectionStatus: {status}).",
                channel=self._broadcast_channel_name,
            )

    ### Handle Incoming Messages ###

    def _handle_message(
        self,
        result: omni.client.Result,
        channel_event: omni.client.ChannelEvent,
        user_id: str,
        content: omni.client.Content,
    ):

        if channel_event == omni.client.ChannelEvent.JOIN:
            pass

        elif channel_event == omni.client.ChannelEvent.MESSAGE:
            try:
                # decode message
                bytes = memoryview(content).tobytes()
                buffer = bytes.decode("utf-8").rstrip("\x00")
                json_data = json.loads(buffer)

                message = messages.WorkerMessage(
                    message_type=json_data["message_type"],
                    message_payload=json_data["message_payload"],
                    message_length=json_data["message_len"],
                    from_name=json_data["from"],
                    to_name=json_data["to"],
                )

                # respond to messages
                if message.type == "attach_worker_request":
                    omni.log.info("Attach worker request received...")
                    if self._recv_uuid is None:
                        self._recv_uuid = message.from_name
                        self._worker_channel_url = omni.client.combine_urls(
                            self._server_path,
                            f"gis_channel_{self._broadcast_channel_name}",
                        )
                        self._send_attach_worker_reply()
                    else:
                        omni.log.error("Another UI instance is using this worker.")

                elif message.type == "attach_worker_decision":
                    omni.log.info(
                        f"Attached worker with UUID <{self._recv_uuid}>. Ready for requests."
                    )
                    accepted = message.payload["worker_accepted"]
                    if accepted and message.to_name == self._uuid:
                        self._worker_prev_time = time.time()
                        self._join_worker_channel()

                elif message.type == "gis_processing_request":
                    self._trigger_job(message.payload)

                elif message.type == "detach_worker_request":
                    self._detach_worker()

                elif message.type == "heartbeat_reply":
                    if message.payload["count"] == 1 and self._current_job:
                        self._job_cancelled = True
                        self._current_job.end_job()

                    self._worker_prev_time = time.time()

            except Exception as e:
                update_payload = messages.gis_update_payload
                update_payload["status"] = "completed"
                update_payload["returncode"] = 100
                update_payload["stdout"] = (
                    f"Failed to handle message. Got exception: {e}"
                )
                self._send_gis_status_update(update_payload)
                omni.log.error(f"Failed to handle message. Got exception: {e}")
                omni.log.info(f"Listening on {self._broadcast_channel_url}...")

    def run_listener(self):
        # Verify connection
        if self._server_path is not None:
            omni.log.info(f"Joining <{self._server_path}>...")
            asyncio.run(self._run_listener())
        else:
            omni.log.error("Broadcast channel url cannot be None.")
            return

    async def _run_listener(self):
        # Check if server is accessible
        omni.log.info(f"Checking if server <{self._server_path}> is accessible...")

        channel_accessible = await self._join_channels_async()
        await asyncio.sleep(0.1)

        if not channel_accessible:
            omni.log.error(
                f"Cannot attach worker because <{self._server_path}> is not accessible."
            )
            return
        else:
            omni.log.info(f"Server <{self._server_path}> accessible.")
            omni.log.info(f"Starting listener...")
            await self._listen_on_channel()

    async def _join_channels_async(self):
        server_accessible = True

        try:
            result, server_info = await omni.client.get_server_info_async(
                self._server_path
            )
            if result != omni.client.Result.OK:
                server_accessible = False
                omni.log.error(
                    f"Failed to join channel <{self._server_path}> as nucleus server is not accessible."
                )

        except Exception as e:
            server_accessible = False
            omni.log.error(
                f"Failed to join channel <{self._server_path}> as user token is invalid: {str(e)}."
            )

        if server_accessible:
            self._join_broadcast_channel()
            return True
        else:
            return False

    def _join_broadcast_channel(self):
        self._broadcast_channel_handler = omni.client.join_channel_with_callback(
            omni.client.combine_urls(self._server_path, self._broadcast_channel_name),
            self._handle_message,
        )

    def _join_worker_channel(self):
        self._worker_channel_handler = omni.client.join_channel_with_callback(
            self._worker_channel_url, self._handle_message
        )

        # start heartbeat process
        self._heartbeat_update_process = subprocess.Popen(
            f"python3 /src/aodt_gis/aodt_py/aodt_ui_gis/gis_jobs/channel_update.py -u {self._worker_channel_url} -i {self._uuid} -r {self._recv_uuid}",
            shell=True,
        )

    async def _listen_on_channel(self):
        omni.log.info(f"Listening on {self._broadcast_channel_url}...")
        while True:
            omni.client.live_process()
            if self._worker_channel_handler is not None:
                if int(time.time()) % WORKER_UPDATE_INTERVAL == 0:
                    curr_time = time.time()
                    if curr_time - self._worker_prev_time > WORKER_CONNECTION_TIMEOUT:
                        try:
                            result, server_info = (
                                await omni.client.get_server_info_async(
                                    self._server_path
                                )
                            )
                            if result != omni.client.Result.OK:
                                omni.log.error(
                                    f"Failed to join channel <{self._server_path}> nucleus server is not accessible."
                                )
                                self._detach_worker()

                        except Exception as e:
                            omni.log.error(
                                f"Failed to join channel <{self._server_path}> as user token is invalid: {str(e)}."
                            )
                            self._detach_worker()

            time.sleep(1)

    def _shut_down_omniverse(self):
        omni.client.live_wait_for_pending_updates()

    ### Messaging ###

    def _send_message(self, channel, message: messages.WorkerMessage):
        if channel is None:
            omni.log.error("Cannot send message as Channel is None.")
            return

        omni.client.send_message(channel.id, message.get_as_json().encode())

    def _send_attach_worker_reply(self):
        self._send_message(
            channel=self._broadcast_channel_handler,
            message=messages.AttachWorkerReply(
                from_name=self._uuid,
                to_name=self._recv_uuid,
                worker_channel=self._worker_channel_url,
            ),
        )

    def _send_gis_status_update(self, update_payload):
        self._send_message(
            channel=self._worker_channel_handler,
            message=messages.GisStatusUpdate(
                from_name=self._uuid,
                to_name=self._recv_uuid,
                _gis_update_payload=update_payload,
            ),
        )

    def _detach_worker(self):
        omni.log.info(
            f"Detached worker with UUID <{self._recv_uuid}>. Returning to main channel..."
        )
        self._recv_uuid = None
        self._worker_channel_handler.stop()
        self._worker_channel_handler = None
        self._heartbeat_update_process.kill()
        self._shut_down_omniverse()
        omni.log.info(f"Listening on {self._broadcast_channel_url}...")

    ### Job trigger ###
    def _job_log(func):
        def wrapper(self, *args):
            job_type = args[0]["job_type"]
            output_stage_path = args[0]["output_stage"]

            # create log dir if it doesn't exist
            Path(LOG_DIR_PATH).mkdir(parents=True, exist_ok=True)

            if job_type == "gml":
                self._current_job = GmlJob()

            elif job_type == "osm":
                self._current_job = OsmJob()

            # Start job
            self._job_in_progress = True
            begin = time.time()
            omni.log.info(
                f"Starting {job_type} job...", channel=self._broadcast_channel_name
            )

            update_payload = messages.gis_update_payload
            update_payload["job_type"] = job_type
            update_payload["status"] = "started"
            self._send_gis_status_update(update_payload)

            # Run job
            func(self, *args, update_payload)

            # End job
            if not self._job_cancelled:
                end = time.time()
                omni.log.info(
                    f"Completed {job_type} job in {end-begin}s",
                    channel=self._broadcast_channel_name,
                )

                update_payload["status"] = "completed"
                update_payload["stdout"] += f"Log: {self._current_job._log_file_path}"
                self._send_gis_status_update(update_payload)
                omni.log.info(
                    f"Listening on {self._broadcast_channel_url}...",
                    channel=self._broadcast_channel_name,
                )
            else:
                omni.log.info(
                    f"Job cancelled from UI.",
                    channel=self._broadcast_channel_name,
                )

                update_payload["status"] = "cancelled"
                self._send_gis_status_update(update_payload)
                omni.log.info(
                    f"Listening on {self._broadcast_channel_url}...",
                    channel=self._broadcast_channel_name,
                )

            del self._current_job
            self._current_job = None
            self._job_in_progress = False
            self._job_cancelled = False

        return wrapper

    @_job_log
    def _trigger_job(self, payload, gis_update_payload):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        if payload["job_type"] == "gml":
            log_file_path = LOG_DIR_PATH + f"gml_{timestamp}.txt"
            f = open(log_file_path, "w")
            f.close()

            job_config = {
                "in_gmls": self._clean_input_file_paths(payload["input_files"]),
                "output_stage": payload["output_stage"],
                "epsg_in": payload["epsg_in"],
                "epsg_out": payload["epsg_out"],
                "disable_interiors": payload["disable_interiors"],
                #"force_mobility": payload["force_mobility"],
                #"textures_out_dir": payload["texture_out_prefix"],
            }

            job_config = {k: v for k, v in job_config.items() if len(str(v)) > 0}

        elif payload["job_type"] == "osm":
            coords_split = payload["coords"].split(",")
            outputFilepath = payload["output_stage"]

            log_file_path = LOG_DIR_PATH + f"osm_{timestamp}.txt"
            f = open(log_file_path, "w")
            f.close()

            job_config = {
                "minLon": float(coords_split[0]),
                "minLat": float(coords_split[1]),
                "maxLon": float(coords_split[2]),
                "maxLat": float(coords_split[3]),
                "output_stage": outputFilepath,
                "disable_interiors": payload["disable_interiors"],
            }

        job_config["_worker_channel_handler"] = self._worker_channel_handler
        job_config["_worker_channel_url"] = self._worker_channel_url
        job_config["_uuid"] = self._uuid
        job_config["_recv_uuid"] = self._recv_uuid
        job_config["_broadcast_channel_name"] = self._broadcast_channel_name

        job_config["_worker_update_interval"] = WORKER_UPDATE_INTERVAL
        job_config["_log_file_path"] = log_file_path

        if self._current_job is not None:
            self._current_job.set(is_connected=True, **job_config)
            gis_update_payload["returncode"], gis_update_payload["stdout"] = (
                self._current_job.run()
            )

        else:
            omni.log.error("Invalid job type requested.")

    def _clean_input_file_paths(self, input_files: str):
        files = input_files.split(" ")
        clean_paths = [str(Path.joinpath(Path("../../"), Path(x))) for x in files]
        return " ".join(clean_paths)


if __name__ == "__main__":
    parser = ArgumentParser(description="")
    parser.add_argument("-o", "--nucleus", type=str, required=True)
    parser.add_argument("-b", "--broadcast", type=str, required=True)
    args = parser.parse_args()

    listener = ChannelListener(args.nucleus, args.broadcast)
    listener.run_listener()
