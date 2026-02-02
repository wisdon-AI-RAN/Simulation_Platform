# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import json


class WorkerMessage:
    def __init__(
        self,
        from_name: str,
        to_name: str,
        message_type: str,
        message_payload: dict = {},
        message_length: int = 0,
    ):
        self.from_name = from_name
        self.to_name = to_name
        self.type = message_type
        self.length = message_length
        self.payload = message_payload

    def __str__(self):
        return f"Message(type={self.type}, payload={self.payload}, length={self.length}, from={self.from_name}, to={self.to_name})"

    def get_as_json(self):
        msg = {
            "from": self.from_name,
            "to": self.to_name,
            "message_type": self.type,
            "message_len": self.length,
            "message_payload": self.payload,
        }
        buf = json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
        return buf

    def get_payload(self, name: str):
        return self.payload.get(name, None)


class AttachWorkerReply(WorkerMessage):
    def __init__(self, from_name="", to_name="", worker_channel=""):
        payload = {
            "worker_channel": worker_channel,
        }
        super().__init__(from_name, to_name, "attach_worker_reply", payload)


gis_update_payload = {
    "status": "",
    "stdout": "",
    "stderr": "",
    "returncode": -1,
    "job_type": "",
}


class GisStatusUpdate(WorkerMessage):
    def __init__(self, from_name="", to_name="", _gis_update_payload={}):
        payload = _gis_update_payload
        super().__init__(from_name, to_name, "gis_status_update", payload)


class GisHeartbeatUpdate(WorkerMessage):
    def __init__(self, from_name: str, to_name: str):
        super().__init__(from_name, to_name, "heartbeat_update")
