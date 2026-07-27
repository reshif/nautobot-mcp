"""GraphQL power tools — the ideal way to traverse the source of truth.

`nautobot_graphql` runs an arbitrary (read-only) GraphQL query, letting the model
fetch exactly the cross-object shape it needs in ONE call (e.g. devices at a site
with their interfaces, IPs, and connected peers). `nautobot_saved_query` runs a
curated, stored query by name — safer/repeatable for common reports.
"""
from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..core.errors import AmbiguousTarget, TargetNotFound
from ._shared import AppContext, Response, ToolResult, register_tool, ro

_GQL_DESC = (
    "Run a read-only GraphQL query against Nautobot — the best tool for rich, cross-object "
    "questions that would otherwise take many calls (e.g. '{ devices(location:\"AMS01\"){ name "
    "role{name} interfaces{ name ip_addresses{ address } connected_endpoint{ ... } } } }'). "
    "Pass the query string and optional variables. Nautobot's GraphQL is read-only. Prefer this "
    "over multiple nautobot_query calls when you need related data together."
)
_SAVED_DESC = (
    "Run a saved (stored) Nautobot GraphQL query by name — repeatable, vetted reports. Pass the "
    "saved query's name and optional variables. Use nautobot_query(object_type='graphql-queries') "
    "to discover available saved queries."
)
_SCHEMA_DESC = (
    "Introspect the Nautobot GraphQL schema so you can write a correct nautobot_graphql query. "
    "Call with no argument to list the top-level query fields (e.g. 'devices', 'interfaces', "
    "'prefixes'); pass a GraphQL type name (e.g. 'DeviceType') to list that type's selectable "
    "fields. Use this BEFORE nautobot_graphql when unsure of field names."
)


async def _graphql(
    app: AppContext,
    query: Annotated[str, Field(description="A read-only GraphQL query string, e.g. '{ devices(location:\"AMS01\"){ name interfaces{ name } } }'. Use nautobot_graphql_schema first if unsure of field names.")],
    variables: Annotated[dict | None, Field(description="Optional GraphQL variables as a dict.")] = None,
) -> ToolResult:
    body = {"query": query, "variables": variables or {}}
    result = await app.gateway.post("graphql/", body)
    errors = result.get("errors") if isinstance(result, dict) else None
    data = result.get("data") if isinstance(result, dict) else result
    if errors:
        return Response.build(f"GraphQL returned {len(errors)} error(s).",
                              {"data": data, "errors": errors}, scope="graphql")
    top = list(data.keys()) if isinstance(data, dict) else []
    return Response.build(f"GraphQL ok; top-level fields: {', '.join(top) or '(none)'}.",
                          {"data": data}, scope="graphql")


async def _saved_query(
    app: AppContext,
    name: Annotated[str, Field(description="Name of a stored GraphQL query (discover them via nautobot_query(object_type='graphql-queries')).")],
    variables: Annotated[dict | None, Field(description="Optional GraphQL variables as a dict.")] = None,
) -> ToolResult:
    gw = app.gateway
    rows = await app.resolver.lookup("extras/graphql-queries/", name, cap=10)
    if not rows:
        raise TargetNotFound(f"No saved GraphQL query named '{name}'.")
    if len(rows) > 1:
        raise AmbiguousTarget(f"'{name}' matched {len(rows)} saved queries.",
                              [{"id": r["id"], "name": r.get("name")} for r in rows])
    qid = rows[0]["id"]
    result = await gw.post(f"extras/graphql-queries/{qid}/run/", {"variables": variables or {}})
    data = result.get("data") if isinstance(result, dict) else result
    return Response.build(f"Ran saved query '{rows[0].get('name')}'.", {"data": data}, scope="graphql")


async def _graphql_schema(
    app: AppContext,
    type_name: Annotated[str | None, Field(description="A GraphQL type name (e.g. 'DeviceType') to list its fields; omit to list the root query fields.")] = None,
) -> ToolResult:
    gw = app.gateway
    if type_name:
        q = ('{ __type(name: "' + type_name.replace('"', "") +
             '") { name fields { name type { name kind ofType { name } } } } }')
        res = await gw.post("graphql/", {"query": q})
        typ = ((res or {}).get("data") or {}).get("__type")
        if not typ:
            return Response.build(f"No GraphQL type '{type_name}'. Call with no argument to list root query fields.",
                                  {"type": type_name}, scope="graphql")
        fields = [{"name": f.get("name"),
                   "type": (f.get("type") or {}).get("name") or ((f.get("type") or {}).get("ofType") or {}).get("name")}
                  for f in (typ.get("fields") or [])]
        return Response.build(f"GraphQL type {type_name}: {len(fields)} field(s).",
                              {"type": type_name, "fields": fields}, scope="graphql", count=len(fields))
    q = "{ __schema { queryType { fields { name } } } }"
    res = await gw.post("graphql/", {"query": q})
    names = sorted(f["name"] for f in (((res or {}).get("data") or {}).get("__schema") or {}).get("queryType", {}).get("fields", []))
    return Response.build(f"{len(names)} top-level GraphQL query fields (write a query with nautobot_graphql).",
                          {"query_fields": names}, scope="graphql", count=len(names))


def register(mcp: FastMCP) -> None:
    register_tool(mcp, _graphql, name="nautobot_graphql", description=_GQL_DESC, annotations=ro("GraphQL query"))
    register_tool(mcp, _saved_query, name="nautobot_saved_query", description=_SAVED_DESC, annotations=ro("Run saved GraphQL query"))
    register_tool(mcp, _graphql_schema, name="nautobot_graphql_schema", description=_SCHEMA_DESC, annotations=ro("GraphQL schema introspection"))
