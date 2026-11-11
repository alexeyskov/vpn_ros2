"""Small shared protocol; no ROS dependency so file integrity can be tested locally."""

import hashlib
import re

TEXT_TOPIC = "/wg_test/text"
IMAGE_TOPIC = "/wg_test/image"
ACK_TOPIC = "/wg_test/ack"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transfer_id(value: str) -> str:
    # IDs become filenames on the receiver; never accept paths from the network.
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}-[0-9]{6,}", value):
        raise ValueError("Invalid transfer id")
    return value


def validate_ack(ack: dict, expected: dict) -> None:
    if ack.get("ok") is not True:
        raise ValueError(f"Receiver rejected transfer: {ack.get('error', 'unknown error')}")
    for key, value in expected.items():
        if ack.get(key) != value:
            raise ValueError(f"ACK {key} mismatch: expected {value!r}, received {ack.get(key)!r}")
