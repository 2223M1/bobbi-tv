# -*- coding: utf-8 -*-
"""Tool: Network IP, Gateway, Subnet, DNS Configuration and Status Viewer."""

import ipaddress
import os
import re
import socket
from typing import Dict, List, Optional

from ..common.kodi_ui import (
    dialog_input,
    dialog_ok,
    dialog_select,
    dialog_textviewer,
    dialog_yesno,
    get_string,
    show_notification,
)
from ..common.logger import debug, error, info
from ..common.os_detect import OSType, get_system_info
from ..common.system_exec import run_command
from .base_tool import BaseTool, ToolRegistry


class NetInterfaceInfo:
    def __init__(self, name: str, ip: str = "", netmask: str = "", gateway: str = "", dns: List[str] = None):
        self.name = name
        self.ip = ip
        self.netmask = netmask
        self.gateway = gateway
        self.dns = dns or []


@ToolRegistry.register
class NetConfigTool(BaseTool):
    id = "net_config"
    title_id = 30004
    description_id = 30401
    icon = "DefaultNetwork.png"
    order = 40

    def run(self, params: Dict[str, str]) -> None:
        title = get_string(30004, "Network Configuration")
        info("Initiating Network Configuration Tool")

        interfaces = self._get_interfaces()
        if not interfaces:
            dialog_ok(title, get_string(30418, "No active network interfaces detected."))
            return

        # Show menu: first view current status, or select interface to configure
        options = [
            f"1. {get_string(30401, 'Current Network Status')}",
            f"2. {get_string(30407, 'Enable DHCP (Auto IP)')}",
            f"3. {get_string(30408, 'Configure Static IP')}",
        ]
        action_idx = dialog_select(title, options)
        if action_idx == 0:
            self._show_network_status(title, interfaces)
        elif action_idx == 1:
            self._configure_dhcp(title, interfaces)
        elif action_idx == 2:
            self._configure_static(title, interfaces)

    def _get_interfaces(self) -> List[NetInterfaceInfo]:
        """Collect network interface information across Linux/CoreELEC/Windows."""
        results = []
        dns_servers = self._get_dns_servers()
        default_gw = self._get_default_gateway()

        # Check Linux sysfs
        net_dir = "/sys/class/net"
        if os.path.isdir(net_dir):
            try:
                for iface in os.listdir(net_dir):
                    if iface == "lo":
                        continue
                    ip, mask = self._get_linux_ip(iface)
                    results.append(NetInterfaceInfo(
                        name=iface,
                        ip=ip,
                        netmask=mask,
                        gateway=default_gw,
                        dns=dns_servers,
                    ))
            except Exception as e:
                error(f"Error reading /sys/class/net: {e}")

        # Fallback using socket / hostname if empty
        if not results:
            try:
                hostname = socket.gethostname()
                host_ip = socket.gethostbyname(hostname)
                results.append(NetInterfaceInfo(
                    name="Default Interface",
                    ip=host_ip,
                    netmask="255.255.255.0",
                    gateway=default_gw,
                    dns=dns_servers,
                ))
            except Exception:
                pass

        return results

    def _get_linux_ip(self, iface: str) -> (str, str):
        """Extract IP and Netmask via ip addr or ifconfig."""
        code, out, _ = run_command(f"ip -4 addr show {iface}")
        if code == 0 and out:
            # Look for inet 192.168.1.100/24
            m = re.search(r"inet\s+([0-9.]+)/(\d+)", out)
            if m:
                ip = m.group(1)
                prefix = int(m.group(2))
                mask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
                return ip, mask
        return "", ""

    def _get_default_gateway(self) -> str:
        """Parse default gateway from /proc/net/route or ip route."""
        route_file = "/proc/net/route"
        if os.path.isfile(route_file):
            try:
                with open(route_file, "r") as f:
                    for line in f.readlines()[1:]:
                        fields = line.strip().split()
                        if len(fields) >= 3 and fields[1] == "00000000":
                            gw_hex = fields[2]
                            octets = [str(int(gw_hex[i:i+2], 16)) for i in (6, 4, 2, 0)]
                            return ".".join(octets)
            except Exception:
                pass

        code, out, _ = run_command("ip route show default")
        if code == 0 and out:
            m = re.search(r"default via ([0-9.]+)", out)
            if m:
                return m.group(1)
        return ""

    def _get_dns_servers(self) -> List[str]:
        """Read nameservers from /etc/resolv.conf."""
        dns = []
        resolv_path = "/etc/resolv.conf"
        if os.path.isfile(resolv_path):
            try:
                with open(resolv_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("nameserver"):
                            parts = line.split()
                            if len(parts) > 1:
                                dns.append(parts[1])
            except Exception:
                pass
        return dns

    def _show_network_status(self, title: str, interfaces: List[NetInterfaceInfo]) -> None:
        lines = [f"=== {get_string(30401, 'Current Network Status')} ===", ""]
        for iface in interfaces:
            lines.append(f"[{get_string(30402, 'Interface: %s') % iface.name}]")
            lines.append(f"  {get_string(30403, 'IP Address: %s') % (iface.ip or 'Not set')}")
            lines.append(f"  {get_string(30404, 'Subnet Mask: %s') % (iface.netmask or '255.255.255.0')}")
            lines.append(f"  {get_string(30405, 'Gateway: %s') % (iface.gateway or 'Not set')}")
            lines.append(f"  {get_string(30406, 'DNS: %s') % (', '.join(iface.dns) if iface.dns else 'Not set')}")
            lines.append("")
        dialog_textviewer(title, "\n".join(lines))

    def _select_interface(self, title: str, interfaces: List[NetInterfaceInfo]) -> Optional[NetInterfaceInfo]:
        if len(interfaces) == 1:
            return interfaces[0]
        options = [f"{i.name} ({i.ip or 'No IP'})" for i in interfaces]
        idx = dialog_select(f"{title} - Select Interface", options)
        if idx >= 0:
            return interfaces[idx]
        return None

    def _configure_dhcp(self, title: str, interfaces: List[NetInterfaceInfo]) -> None:
        iface = self._select_interface(title, interfaces)
        if not iface:
            return

        if not dialog_yesno(title, get_string(30416, "Switch interface '%s' to DHCP?") % iface.name):
            return

        sys_info = get_system_info()
        success = False
        err_msg = ""

        if sys_info.os_type in (OSType.COREELEC, OSType.LIBREELEC):
            # ConnMan configuration
            service = self._find_connman_service(iface.name)
            if service:
                code, _, err = run_command(f"connmanctl config {service} --ipv4 dhcp")
                success = (code == 0)
                err_msg = err
            else:
                err_msg = "Could not find ConnMan service for interface"
        else:
            # Generic Linux fallback
            code, _, err = run_command(f"dhclient -r {iface.name} && dhclient {iface.name}")
            success = (code == 0)
            err_msg = err

        if success:
            show_notification(title, get_string(30412, "Network settings applied successfully."))
        else:
            dialog_ok(title, get_string(30413, "Network configuration failed: %s") % err_msg)

    def _configure_static(self, title: str, interfaces: List[NetInterfaceInfo]) -> None:
        iface = self._select_interface(title, interfaces)
        if not iface:
            return

        # 1. IP
        new_ip = dialog_input(get_string(30409, "Enter IP address:"), default=iface.ip or "192.168.1.100")
        if not new_ip or not self._is_valid_ipv4(new_ip):
            dialog_ok(title, get_string(30414, "Invalid IP address format."))
            return

        # 2. Netmask
        new_mask = dialog_input(get_string(30415, "Enter Netmask:"), default=iface.netmask or "255.255.255.0")
        if not new_mask or not self._is_valid_ipv4(new_mask):
            dialog_ok(title, get_string(30414, "Invalid IP address format."))
            return

        # 3. Gateway
        new_gw = dialog_input(get_string(30410, "Enter Gateway:"), default=iface.gateway or "192.168.1.1")
        if not new_gw or not self._is_valid_ipv4(new_gw):
            dialog_ok(title, get_string(30414, "Invalid IP address format."))
            return

        # 4. DNS
        default_dns_str = ", ".join(iface.dns) if iface.dns else f"{new_gw}, 223.5.5.5"
        new_dns_str = dialog_input(get_string(30411, "Enter DNS (comma separated):"), default=default_dns_str)
        dns_list = [d.strip() for d in new_dns_str.split(",") if self._is_valid_ipv4(d.strip())]

        # Confirmation
        summary = (
            f"Interface: {iface.name}\n"
            f"IP: {new_ip}\n"
            f"Netmask: {new_mask}\n"
            f"Gateway: {new_gw}\n"
            f"DNS: {', '.join(dns_list)}\n\n"
            f"{get_string(30417, 'Apply these static network settings?')}"
        )
        if not dialog_yesno(title, summary):
            return

        sys_info = get_system_info()
        success = False
        err_msg = ""

        if sys_info.os_type in (OSType.COREELEC, OSType.LIBREELEC):
            service = self._find_connman_service(iface.name)
            if service:
                dns_args = f"--nameservers {' '.join(dns_list)}" if dns_list else ""
                cmd = f"connmanctl config {service} --ipv4 manual {new_ip} {new_mask} {new_gw} {dns_args}".strip()
                code, _, err = run_command(cmd)
                success = (code == 0)
                err_msg = err
            else:
                err_msg = "Could not find ConnMan service for interface"
        else:
            # Generic Linux fallback
            cidr = self._netmask_to_cidr(new_mask)
            cmd = f"ip addr flush dev {iface.name} && ip addr add {new_ip}/{cidr} dev {iface.name} && ip route add default via {new_gw}"
            code, _, err = run_command(cmd)
            success = (code == 0)
            err_msg = err

        if success:
            show_notification(title, get_string(30412, "Network settings applied successfully."))
        else:
            dialog_ok(title, get_string(30413, "Network configuration failed: %s") % err_msg)

    def _find_connman_service(self, iface_name: str) -> Optional[str]:
        """Find the ConnMan service name associated with an interface (e.g. ethernet_001122334455_cable)."""
        code, out, _ = run_command("connmanctl services")
        if code == 0 and out:
            for line in out.splitlines():
                if "ethernet_" in line or "wifi_" in line:
                    parts = line.split()
                    if parts:
                        return parts[-1]
        return None

    def _is_valid_ipv4(self, ip_str: str) -> bool:
        try:
            ipaddress.IPv4Address(ip_str.strip())
            return True
        except ValueError:
            return False

    def _netmask_to_cidr(self, mask_str: str) -> int:
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{mask_str}").prefixlen
        except Exception:
            return 24
