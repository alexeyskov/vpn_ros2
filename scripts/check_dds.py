"""Start a real ROS node with the generated DDS settings on loopback.

Used during Docker builds to catch XML settings rejected by the installed DDS
version. Only interface/peer addresses change; production still requires wg0.
"""

import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import rclpy
from rclpy.context import Context

from configure_dds import make_config


def main():
    namespace = {"c": "https://cdds.io/config"}
    root = ET.fromstring(make_config("10.10.0.4", "10.10.0.3"))
    interface = root.find(".//c:NetworkInterface", namespace)
    interface.set("name", "lo")
    interface.set("address", "127.0.0.1")
    root.find(".//c:Peer", namespace).set("Address", "127.0.0.1")
    # Preserve the default namespace expected by the Cyclone DDS XML parser.
    ET.register_namespace("", namespace["c"])
    with tempfile.TemporaryDirectory(prefix="wg-dds-check-") as directory:
        path = Path(directory) / "cyclonedds.xml"
        path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
        os.environ["CYCLONEDDS_URI"] = path.as_uri()
        os.environ["RMW_IMPLEMENTATION"] = "rmw_cyclonedds_cpp"
        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "SYSTEM_DEFAULT"
        os.environ["ROS_DOMAIN_ID"] = "230"
        os.environ.pop("ROS_LOCALHOST_ONLY", None)
        context = Context()
        node = None
        try:
            rclpy.init(context=context)
            node = rclpy.create_node("wg_dds_config_check", context=context)
            print("PASS: generated DDS configuration accepted by a real ROS 2 node", flush=True)
        finally:
            if node is not None:
                node.destroy_node()
            context.try_shutdown()


if __name__ == "__main__":
    main()
