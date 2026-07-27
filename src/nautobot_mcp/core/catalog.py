"""The object-type catalog — one source of truth for Nautobot's domain surface.

Three consumers used to each hardcode their own object-type→path map (the query
tool's 75-type list, the resolver's name-resolvable kinds, the audit log's
content-type aliases). They now all derive from here, so adding an object type or
a plugin app is a single edit in one file — the mature-hierarchy invariant.

- PATHS         : friendly object_type -> REST collection path (the broad surface)
- RESOLVABLE    : singular kind -> (path, exact-match filter field) for name→object
- CONTENT_TYPES : friendly alias -> Nautobot content-type label (for change audit)
"""
from __future__ import annotations

# friendly object_type -> REST collection path. Curated to the types infra/delivery use.
PATHS: dict[str, str] = {
    # DCIM
    "devices": "dcim/devices/", "interfaces": "dcim/interfaces/", "locations": "dcim/locations/",
    "location-types": "dcim/location-types/", "racks": "dcim/racks/", "rack-groups": "dcim/rack-groups/",
    "cables": "dcim/cables/", "device-types": "dcim/device-types/", "manufacturers": "dcim/manufacturers/",
    "platforms": "dcim/platforms/", "inventory-items": "dcim/inventory-items/", "modules": "dcim/modules/",
    "console-ports": "dcim/console-ports/", "power-ports": "dcim/power-ports/", "power-feeds": "dcim/power-feeds/",
    "power-panels": "dcim/power-panels/", "front-ports": "dcim/front-ports/", "rear-ports": "dcim/rear-ports/",
    "controllers": "dcim/controllers/", "virtual-chassis": "dcim/virtual-chassis/",
    "software-versions": "dcim/software-versions/", "device-redundancy-groups": "dcim/device-redundancy-groups/",
    # IPAM
    "prefixes": "ipam/prefixes/", "ip-addresses": "ipam/ip-addresses/", "vlans": "ipam/vlans/",
    "vlan-groups": "ipam/vlan-groups/", "vrfs": "ipam/vrfs/", "namespaces": "ipam/namespaces/",
    "services": "ipam/services/", "rirs": "ipam/rirs/", "route-targets": "ipam/route-targets/",
    # Circuits / Virtualization / Tenancy / Cloud / Wireless
    "circuits": "circuits/circuits/", "providers": "circuits/providers/",
    "circuit-terminations": "circuits/circuit-terminations/", "provider-networks": "circuits/provider-networks/",
    "clusters": "virtualization/clusters/", "virtual-machines": "virtualization/virtual-machines/",
    "vm-interfaces": "virtualization/interfaces/", "cluster-groups": "virtualization/cluster-groups/",
    "tenants": "tenancy/tenants/", "tenant-groups": "tenancy/tenant-groups/",
    "cloud-accounts": "cloud/cloud-accounts/", "cloud-networks": "cloud/cloud-networks/",
    "cloud-services": "cloud/cloud-services/",
    "wireless-networks": "wireless/wireless-networks/", "radio-profiles": "wireless/radio-profiles/",
    # Extras (governance / SoT metadata)
    "statuses": "extras/statuses/", "roles": "extras/roles/", "tags": "extras/tags/",
    "jobs": "extras/jobs/", "job-results": "extras/job-results/", "config-contexts": "extras/config-contexts/",
    "dynamic-groups": "extras/dynamic-groups/", "relationships": "extras/relationships/",
    "graphql-queries": "extras/graphql-queries/", "git-repositories": "extras/git-repositories/",
    "secrets": "extras/secrets/", "contacts": "extras/contacts/", "teams": "extras/teams/",
    "custom-fields": "extras/custom-fields/",
    # VPN / load-balancer / data-validation apps
    "vpns": "vpn/vpns/", "vpn-tunnels": "vpn/vpn-tunnels/", "vpn-profiles": "vpn/vpn-profiles/",
    "virtual-servers": "load-balancers/virtual-servers/", "lb-pools": "load-balancers/load-balancer-pools/",
    "health-check-monitors": "load-balancers/health-check-monitors/",
    "data-compliance": "data-validation/data-compliance/",
    # Golden Config app
    "config-compliance": "plugins/golden-config/config-compliance/",
    "golden-config-backups": "plugins/golden-config/golden-config/",
    "compliance-rules": "plugins/golden-config/compliance-rule/",
    "config-plans": "plugins/golden-config/config-plan/",
    # Device Lifecycle app
    "cves": "plugins/nautobot-device-lifecycle-mgmt/cve/",
    "hardware-notices": "plugins/nautobot-device-lifecycle-mgmt/hardware/",
    "lifecycle-software": "plugins/nautobot-device-lifecycle-mgmt/software/",
    "support-contracts": "plugins/nautobot-device-lifecycle-mgmt/contract/",
}

# resolver kinds: singular kind -> (REST path, exact-match filter field).
# IP/prefix resolve on their value fields; the rest on `name`.
RESOLVABLE: dict[str, tuple[str, str]] = {
    "device": (PATHS["devices"], "name"),
    "location": (PATHS["locations"], "name"),
    "vlan": (PATHS["vlans"], "name"),
    "prefix": (PATHS["prefixes"], "prefix"),
    "ip": (PATHS["ip-addresses"], "address"),
}

# change-audit friendly alias -> Nautobot content-type label.
CONTENT_TYPES: dict[str, str] = {
    "device": "dcim.device", "interface": "dcim.interface", "location": "dcim.location",
    "prefix": "ipam.prefix", "ip": "ipam.ipaddress", "ip-address": "ipam.ipaddress",
    "vlan": "ipam.vlan", "cable": "dcim.cable", "rack": "dcim.rack",
}

# Filter discoverability: Nautobot 400s on an unknown filter field but never says which are
# valid. We surface the common, high-value filters per object type so the query tool can guide
# the LLM (in its description and when a filter is rejected). Not exhaustive — `q` free-text
# and object-specific fields exist too — but covers the filters infra/delivery reach for.
BASE_FILTERS: tuple[str, ...] = ("q", "id", "name", "tag", "status", "tenant")

TYPE_FILTERS: dict[str, tuple[str, ...]] = {
    "devices": ("location", "role", "manufacturer", "device_type", "platform", "rack",
                "serial", "has_primary_ip", "software_version"),
    "interfaces": ("device", "device_id", "enabled", "type", "mgmt_only", "lag"),
    "prefixes": ("location", "role", "namespace", "vrf", "vlan", "within", "within_include",
                 "prefix_length", "ip_version"),
    "ip-addresses": ("parent", "namespace", "vrf", "role", "type", "dns_name", "has_interface_assignments"),
    "vlans": ("location", "vlan_group", "vid", "role"),
    "racks": ("location", "rack_group", "role", "serial"),
    "circuits": ("provider", "location", "circuit_type", "cid"),
    "virtual-machines": ("cluster", "location", "role", "platform", "status"),
    "cables": ("device", "location", "type", "termination_a_type"),
    "config-compliance": ("device", "device__location", "compliance", "rule"),
    "cves": ("severity", "status", "affected_softwares"),
}


def filters_for(object_type: str) -> list[str]:
    """Common valid filter names for an object type (base + type-specific), sorted."""
    return sorted(set(BASE_FILTERS) | set(TYPE_FILTERS.get(object_type, ())))
