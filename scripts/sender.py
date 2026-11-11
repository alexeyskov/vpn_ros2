"""Client2: publish text and raw OpenCV/NumPy pixels; require receiver ACKs."""

import json
import math
import os
import time
import uuid

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from protocol import ACK_TOPIC, IMAGE_TOPIC, TEXT_TOPIC, digest, validate_ack
from ros_common import reliable_qos


class Sender(Node):
    def __init__(self):
        super().__init__("wg_test_sender")
        self.text_pub = self.create_publisher(String, TEXT_TOPIC, reliable_qos())
        self.image_pub = self.create_publisher(Image, IMAGE_TOPIC, reliable_qos())
        self.create_subscription(String, ACK_TOPIC, self.on_ack, reliable_qos())
        self.pending_id = None
        self.acks = {}

    def on_ack(self, message):
        try:
            ack = json.loads(message.data)
            if isinstance(ack, dict) and ack.get("id") == self.pending_id and ack.get("kind") in ("text", "image"):
                self.acks[ack["kind"]] = ack
        except (ValueError, TypeError):
            self.get_logger().warning("Ignoring malformed ACK")

    def wait_for(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while rclpy.ok():
            if predicate():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            rclpy.spin_once(self, timeout_sec=min(0.1, remaining))
        return False

    def run(self):
        path = os.environ.get("IMAGE_PATH", "/data/resources/Canon80D_8_8_12800_printer_14_real.jpg")
        image = cv2.imread(path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Cannot read image: {path}")
        text = os.environ.get("MESSAGE_TEXT", "Привет от Client2 через WireGuard!")
        count = int(os.environ.get("SEND_COUNT", "5"))
        retries = int(os.environ.get("SEND_RETRIES", "3"))
        interval = float(os.environ.get("SEND_INTERVAL", "1"))
        ack_timeout = float(os.environ.get("ACK_TIMEOUT", "15"))
        discovery_timeout = float(os.environ.get("DISCOVERY_TIMEOUT", "60"))
        if count < 0 or retries < 1 or not math.isfinite(interval) or interval < 0:
            raise ValueError("SEND_COUNT >= 0, SEND_RETRIES >= 1, SEND_INTERVAL >= 0 required")
        if not all(math.isfinite(t) and t > 0 for t in (ack_timeout, discovery_timeout)):
            raise ValueError("ACK_TIMEOUT and DISCOVERY_TIMEOUT must be positive finite seconds")
        self.get_logger().info(f"Waiting for Client1; image={list(image.shape)}, {image.nbytes} raw bytes")
        ready = lambda: (self.text_pub.get_subscription_count() > 0
                         and self.image_pub.get_subscription_count() > 0
                         and self.count_publishers(ACK_TOPIC) > 0)
        if not self.wait_for(ready, discovery_timeout):
            raise TimeoutError("Client1 not discovered. Check WG handshake, server forwarding, and matching ROS_DOMAIN_ID.")
        bridge = CvBridge()
        session = uuid.uuid4().hex
        sequence = 0
        while rclpy.ok() and (count == 0 or sequence < count):
            sequence += 1
            self.pending_id = f"{session}-{sequence:06d}"
            self.acks.clear()
            text_message = String(data=json.dumps({"id": self.pending_id, "text": text}, ensure_ascii=False))
            image_message = bridge.cv2_to_imgmsg(image, encoding="bgr8")
            image_message.header.frame_id = self.pending_id
            image_message.header.stamp = self.get_clock().now().to_msg()
            expected = {
                "text": {"id": self.pending_id, "kind": "text", "sha256": digest(text.encode("utf-8"))},
                "image": {"id": self.pending_id, "kind": "image", "sha256": digest(image.tobytes()),
                          "shape": list(image.shape), "bytes": image.nbytes},
            }
            for attempt in range(1, retries + 1):
                if "text" not in self.acks:
                    self.text_pub.publish(text_message)
                if "image" not in self.acks:
                    self.image_pub.publish(image_message)
                self.wait_for(lambda: len(self.acks) == 2 or any(a.get("ok") is not True for a in self.acks.values()), ack_timeout)
                for kind, ack in self.acks.items():
                    validate_ack(ack, expected[kind])
                if len(self.acks) == 2:
                    break
                missing = sorted(set(expected) - self.acks.keys())
                self.get_logger().warning(f"ACK timeout {self.pending_id}, attempt {attempt}/{retries}, missing={missing}")
            else:
                raise TimeoutError(f"No verified delivery for {self.pending_id}")
            self.get_logger().info(f"PASS {sequence}: text + image saved on Client1, sha256={expected['image']['sha256']}")
            if count == 0 or sequence < count:
                self.wait_for(lambda: False, interval)
        self.get_logger().info(f"SUCCESS: {sequence} text/image pairs verified")


def main():
    rclpy.init()
    node = None
    status = 0
    try:
        node = Sender()
        node.run()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        status = 130
    except Exception as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(str(exc), flush=True)
        status = 1
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
