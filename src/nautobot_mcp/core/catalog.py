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
