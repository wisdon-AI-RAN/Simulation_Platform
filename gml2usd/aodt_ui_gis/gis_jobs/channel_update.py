from argparse import ArgumentParser
import time
import omni.client  # type: ignore
import omni.log  # type: ignore
import messages

WORKER_HEARTBEAT_INTERVAL = 2  # seconds


class ChannelHearbeatUpdates:
    def __init__(self, url, uuid, recv_uuid):
        self._worker_channel_url = url
        self._uuid = uuid
        self._recv_uuid = recv_uuid
        self._worker_channel_handler = None

    def _join_worker_channel(self):
        self._worker_channel_handler = omni.client.join_channel_with_callback(
            self._worker_channel_url, self._handle_message
        )

    def _handle_message(
        self,
        result: omni.client.Result,
        channel_event: omni.client.ChannelEvent,
        user_id: str,
        content: omni.client.Content,
    ):

        pass

    def _send_message(self, channel, message: messages.WorkerMessage):
        if channel is None:
            omni.log.error("Cannot send message as Channel is None.")
            return

        omni.client.send_message(channel.id, message.get_as_json().encode())

    def _send_heartbeat_update(self):
        self._send_message(
            channel=self._worker_channel_handler,
            message=messages.GisHeartbeatUpdate(
                from_name=self._uuid,
                to_name=self._recv_uuid,
            ),
        )

    def run_updates(self):
        self._join_worker_channel()
        while True:
            if int(time.time()) % WORKER_HEARTBEAT_INTERVAL == 0:
                # Sends a heartbeat update regularly to the UI
                self._send_heartbeat_update()
            time.sleep(1)


if __name__ == "__main__":
    parser = ArgumentParser(description="")
    parser.add_argument("-u", "--url", type=str, required=True)
    parser.add_argument("-i", "--uuid", type=str, required=True)
    parser.add_argument("-r", "--recv_uuid", type=str, required=True)
    args = parser.parse_args()

    updates = ChannelHearbeatUpdates(args.url, args.uuid, args.recv_uuid)
    updates.run_updates()
