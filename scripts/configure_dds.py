"""Refuse a non-WireGuard route and generate the Cyclone DDS configuration."""

import ipaddress
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def make_config(local_ip: str, peer_ip: str) -> str:
    local = ipaddress.IPv4Address(local_ip)
    peer = ipaddress.IPv4Address(peer_ip)
    if local == peer or any(ip.is_unspecified or ip.is_multicast or ip.is_loopback for ip in (local, peer)):
        raise ValueError("Expected two different unicast WireGuard IPv4 addresses")
    root = ET.Element("CycloneDDS", xmlns="https://cdds.io/config")
    domain = ET.SubElement(root, "Domain", Id="any")
    general = ET.SubElement(domain, "General")
    interfaces = ET.SubElement(general, "Interfaces")
    ET.SubElement(interfaces, "NetworkInterface", name="wg0", address=str(local),
                  multicast="false", presence_required="true")
    ET.SubElement(general, "AllowMulticast").text = "false"
    # Cyclone DDS calls UDP/IPv4 "udp"; "udp4" is not a valid XML value.
    ET.SubElement(general, "Transport").text = "udp"
    # Leave room for RTPS/UDP/IP headers inside the configured WG MTU of 1420.
    ET.SubElement(general, "FragmentSize").text = "1200B"
    ET.SubElement(general, "MaxMessageSize").text = "1380B"
    ET.SubElement(general, "MaxRexmitMessageSize").text = "1380B"
    discovery = ET.SubElement(domain, "Discovery")
    ET.SubElement(discovery, "ParticipantIndex").text = "auto"
    ET.SubElement(discovery, "MaxAutoParticipantIndex").text = "32"
    peers = ET.SubElement(discovery, "Peers")
    ET.SubElement(peers, "Peer", Address=str(peer))
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


def check_route(routes: list, local_ip: str) -> None:
    if not routes or routes[0].get("dev") != "wg0" or routes[0].get("prefsrc") != local_ip:
        raise RuntimeError(f"DDS requires a route through wg0 with source {local_ip}: {routes}")


def interface_ipv4(interfaces: list) -> str:
    addresses = [address["local"]
                 for interface in interfaces if interface.get("ifname") == "wg0"
                 for address in interface.get("addr_info", [])
                 if address.get("family") == "inet"]
    if len(addresses) != 1:
        raise RuntimeError(f"Expected one IPv4 address on wg0, found {addresses}; set WG_LOCAL_IP explicitly if needed")
    return str(ipaddress.IPv4Address(addresses[0]))


def main() -> None:
    peer = os.environ["WG_PEER_IP"]
    local = os.environ.get("WG_LOCAL_IP", "").strip()
    if not local:
        interfaces = json.loads(subprocess.check_output(
            ["ip", "-j", "-4", "address", "show", "dev", "wg0"], text=True))
        local = interface_ipv4(interfaces)
    config = make_config(local, peer)
    routes = json.loads(subprocess.check_output(["ip", "-j", "-4", "route", "get", peer], text=True))
    check_route(routes, local)
    Path("/tmp/cyclonedds.xml").write_text(config)
    print(f"DDS: wg0 ({local}) -> {peer}, unicast, ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '0')}", flush=True)


if __name__ == "__main__":
    main()
