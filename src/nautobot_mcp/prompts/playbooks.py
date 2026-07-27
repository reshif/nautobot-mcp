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

    @mcp.prompt(title="Prefix / subnet report")
    def prefix_report(prefix: str) -> str:
        return (f"{_HOUSE}\nReport on prefix '{prefix}': nautobot_prefix('{prefix}'). State status, role, "
                "namespace/VRF, VLAN, the IP count and child prefixes, and the first free IP(s). If it's nearly "
                "full, say so.")

    @mcp.prompt(title="VLAN report")
    def vlan_report(vlan: str) -> str:
        return (f"{_HOUSE}\nReport on VLAN '{vlan}': nautobot_vlan('{vlan}'). Give its VID, name, status, group, "
                "role, and the prefixes/subnets mapped to it. If the name/VID is ambiguous, ask which one.")

    @mcp.prompt(title="What is it connected to?")
    def connectivity(device: str) -> str:
        return (f"{_HOUSE}\nShow the physical connectivity of '{device}': nautobot_cabling('{device}'). List each "
                "cabled interface, the remote device/port, and reachability. For a specific port use "
                "nautobot_interface('{device}', <name>).")

    @mcp.prompt(title="Find free capacity")
    def capacity(prefix: str = "", location: str = "") -> str:
        pf = f"the next free IPs and child blocks in '{prefix}' with nautobot_ip_allocate('{prefix}')" if prefix else ""
        vl = f"the next free VLAN ID at '{location}' with nautobot_vlan_allocate(location='{location}')" if location else ""
        want = " and ".join(x for x in (pf, vl) if x) or "free IP space (ask for a prefix) or a free VLAN (ask for a site/group)"
        return (f"{_HOUSE}\nSuggest {want}. These are read-only suggestions — the user must reserve them in "
                "Nautobot to make them authoritative.")

    @mcp.prompt(title="Recent changes")
    def change_history(object_type: str = "", days: str = "7") -> str:
        scope = f" to {object_type}" if object_type else ""
        return (f"{_HOUSE}\nSummarize source-of-truth changes{scope} in the last {days} days: "
                f"nautobot_object_changes(object_type='{object_type}', days={days}). Report who changed what, "
                "when, and the action, newest first.")

    @mcp.prompt(title="Config compliance check")
    def compliance_check(device: str = "", location: str = "") -> str:
        target = f"device '{device}'" if device else (f"site '{location}'" if location else "the org")
        arg = f"device='{device}'" if device else (f"location='{location}'" if location else "")
        return (f"{_HOUSE}\nCheck Golden Config compliance for {target}: nautobot_config_compliance({arg}). "
                "Report which features are non-compliant and the remediation. (Requires the Golden Config app / "
                "optional tools enabled.)")
