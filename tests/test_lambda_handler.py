"""Tests for the stateless Streamable HTTP Lambda handler."""

import json
from unittest.mock import patch

from mcp_justwatch.lambda_handler import lambda_handler


def _post(payload):
    event = {"requestContext": {"http": {"method": "POST"}}, "body": json.dumps(payload)}
    response = lambda_handler(event, None)
    return response["statusCode"], json.loads(response["body"]) if response["body"] else None


def _rpc(method, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}


def test_initialize_negotiates_protocol_version():
    status, body = _post(_rpc("initialize", {"protocolVersion": "2025-06-18"}))
    assert status == 200
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert body["result"]["capabilities"] == {"tools": {"listChanged": False}}


def test_notification_gets_202():
    status, body = _post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert status == 202 and body is None


def test_tools_list_comes_from_fastmcp():
    _, body = _post(_rpc("tools/list"))
    tools = {t["name"]: t for t in body["result"]["tools"]}
    assert set(tools) == {"search_content", "get_details", "get_offers_for_countries"}
    assert tools["search_content"]["inputSchema"]["required"] == ["query"]


@patch("mcp_justwatch.server.justwatch.search", return_value=[])
def test_tools_call(mock_search):
    _, body = _post(_rpc("tools/call", {"name": "search_content", "arguments": {"query": "x"}}))
    result = body["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"] == "No results found for 'x' in US."
    mock_search.assert_called_once()


def test_tools_call_invalid_arguments_is_tool_error():
    _, body = _post(_rpc("tools/call", {"name": "search_content", "arguments": {}}))
    assert body["result"]["isError"] is True


def test_unknown_tool_and_method():
    _, body = _post(_rpc("tools/call", {"name": "nope", "arguments": {}}))
    assert body["error"]["code"] == -32602
    _, body = _post(_rpc("resources/list"))
    assert body["error"]["code"] == -32601


def test_batch_and_parse_error():
    status, body = _post([_rpc("ping", id_=1), _rpc("ping", id_=2)])
    assert status == 200 and [r["id"] for r in body] == [1, 2]
    response = lambda_handler({"requestContext": {"http": {"method": "POST"}}, "body": "{"}, None)
    assert response["statusCode"] == 400


def test_get_without_sse_returns_pointer():
    event = {"requestContext": {"http": {"method": "GET"}}, "headers": {"accept": "text/html"}}
    assert lambda_handler(event, None)["statusCode"] == 200
    event["headers"]["accept"] = "text/event-stream"
    assert lambda_handler(event, None)["statusCode"] == 405
