"""Client1: receive ROS text/images, save them, and acknowledge their checksums."""

import json
import os
from pathlib import Path

from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from protocol import ACK_TOPIC, IMAGE_TOPIC, TEXT_TOPIC, transfer_id
from ros_common import reliable_qos
from storage import save_image, save_text


class Receiver(Node):
    def __init__(self):
        super().__init__("wg_test_receiver")
        self.output = Path(os.environ.get("OUTPUT_DIR", "received"))
        self.output.mkdir(parents=True, exist_ok=True)
        self.bridge = CvBridge()
        self.ack_pub = self.create_publisher(String, ACK_TOPIC, reliable_qos())
        self.create_subscription(String, TEXT_TOPIC, self.on_text, reliable_qos())
        self.create_subscription(Image, IMAGE_TOPIC, self.on_image, reliable_qos())
        self.get_logger().info(f"READY: listening on {TEXT_TOPIC}, {IMAGE_TOPIC}; saving to {self.output}")

    def ack(self, result):
        self.ack_pub.publish(String(data=json.dumps(result, ensure_ascii=False)))

    def failure(self, kind, identifier, exc):
        self.get_logger().error(f"{kind} {identifier}: {exc}")
        if identifier:
            self.ack({"id": identifier, "kind": kind, "ok": False, "error": str(exc)})

    def on_text(self, message):
        identifier = None
        try:
            packet = json.loads(message.data)
            identifier = transfer_id(packet["id"])
            text = packet["text"]
            self.ack(save_text(self.output, identifier, text))
            self.get_logger().info(f"TEXT {identifier}: {text}")
        except Exception as exc:
            self.failure("text", identifier, exc)

    def on_image(self, message):
        identifier = None
        try:
            identifier = transfer_id(message.header.frame_id)
            if message.encoding != "bgr8":
                raise ValueError(f"Expected bgr8, got {message.encoding}")
            image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            result = save_image(self.output, identifier, image)
            self.ack(result)
            self.get_logger().info(f"IMAGE {identifier}: {result['shape']}, sha256={result['sha256']}, saved {result['file']}")
        except Exception as exc:
            self.failure("image", identifier, exc)


def main():
    rclpy.init()
    node = None
    try:
        node = Receiver()
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
