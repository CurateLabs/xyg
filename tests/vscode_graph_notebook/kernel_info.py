"""Read kernel identity through the authenticated standard Jupyter channels API.

No code is executed and no connection/HMAC file is opened. The private token
stays in the process environment and authentication header, never the URL/log.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import quote

import websocket
from jupyter_client.session import Session


def encode(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported control message value")


origin = os.environ["XYG_NOTEBOOK_SERVER"]
url = (
    origin.replace("http://", "ws://", 1)
    + "/api/kernels/"
    + quote(sys.argv[1], safe="")
    + "/channels"
)
connection = websocket.create_connection(
    url,
    origin=origin,
    timeout=5,
    header=["Authorization: token " + os.environ["XYG_NOTEBOOK_TOKEN"]],
)
try:
    message = Session().msg("kernel_info_request")
    message["channel"] = "shell"
    connection.send(json.dumps(message, default=encode))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        raw = connection.recv()
        if not isinstance(raw, str):
            continue
        reply = json.loads(raw)
        if (
            reply.get("header", {}).get("msg_type") == "kernel_info_reply"
            and reply.get("parent_header", {}).get("msg_id") == message["header"]["msg_id"]
        ):
            content = reply["content"]
            result = {
                key: content[key]
                for key in (
                    "status",
                    "protocol_version",
                    "implementation",
                    "implementation_version",
                )
            }
            result["language_info"] = {
                key: content["language_info"][key] for key in ("name", "version")
            }
            print(json.dumps(result))
            break
    else:
        raise RuntimeError("actual kernel did not answer its identity request")
finally:
    connection.close()
