"""MCP prompts — packaged, consistent playbooks (source-of-truth workflows)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..config import Settings

_HOUSE = ("Read-only Nautobot (network source of truth). Pass names (not IDs); if a name is "
          "ambiguous the tool returns the candidates — ask the user which. Answer with the "
          "one-line summary first, then detail. Nautobot is intended state, which may differ "
          "from the live network.")


def register_prompts(mcp: FastMCP, _settings: Settings) -> None:
    @mcp.prompt(title="Find an object")
    def find(query: str) -> str:
        return f"{_HOUSE}\nFind '{query}': call nautobot_find(query='{query}'). Report matches per type with their names/IDs."

    @mcp.prompt(title="Device report")
    def device_report(device: str) -> str:
        return (f"{_HOUSE}\nReport on device '{device}': 1) nautobot_device('{device}') for its record. "
                f"2) nautobot_device_interfaces('{device}') for interfaces. 3) nautobot_cabling('{device}') for "
                "connections. Summarise role/type/location/status, key interfaces, and what it connects to.")

    @mcp.prompt(title="IP lookup")
    def ip_lookup(address: str) -> str:
        return (f"{_HOUSE}\nLook up IP '{address}': nautobot_ip_lookup('{address}'). State the status, the parent "
                "prefix, and the device/interface it's assigned to (or that it's unassigned).")

    @mcp.prompt(title="Site inventory")
    def site_inventory(location: str) -> str:
        return (f"{_HOUSE}\nInventory site '{location}': call nautobot_site_report('{location}') for the full picture "
                "(devices by role/status, prefixes, VLANs, racks, data-quality gaps). Summarise it; if gaps exist, "
                "suggest nautobot_data_quality_audit for detail.")

    @mcp.prompt(title="Data-quality audit")
    def data_quality(location: str = "") -> str:
        loc = f"('{location}')" if location else "()"
        return (f"{_HOUSE}\nAudit source-of-truth data quality: nautobot_data_quality_audit{loc}. Report the gaps "
                "ranked by count (devices missing primary IP / rack / platform / software version; prefixes without "
                "roles; unassigned IPs) and recommend what to fix first.")

    @mcp.prompt(title="Device deployment readiness")
    def device_readiness(device: str) -> str:
        return (f"{_HOUSE}\nCheck deployment readiness for '{device}': nautobot_device_readiness('{device}'). "
                "Report GO/NO-GO with the specific missing documentation, and note recent changes.")
