
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import gateway


client = TestClient(gateway.app)

VIEWER = {"Authorization": "Bearer demo-viewer-token"}
ADMIN = {"Authorization": "Bearer demo-admin-token"}


def rpc_request(method, params=None, request_id=1):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params if params is not None else {}
    }


@pytest.fixture
def downstream(monkeypatch):
    """Mock the downstream HTTP server and count calls."""

    received = []
    original_client = httpx.AsyncClient

    def handle_request(request):
        payload = json.loads(request.content)
        received.append(payload)

        if payload["method"] == "tools/list":
            result = {
                "tools": [
                    {"name": "get_customer_record"},
                    {"name": "admin_reset_key"}
                ]
            }
        else:
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": "Executed tool: "
                        + payload["params"]["name"]
                    }
                ],
                "isError": False
            }

        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": result
            }
        )

    transport = httpx.MockTransport(handle_request)

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(gateway.httpx, "AsyncClient", mock_client)

    return received


def test_viewer_cannot_call_admin_tool(downstream):
    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=rpc_request(
            "tools/call",
            {"name": "admin_reset_key", "arguments": {}}
        )
    )

    assert response.json()["error"]["code"] == -32001

    # Most important security assertion:
    assert len(downstream) == 0


def test_admin_can_call_admin_tool(downstream):
    response = client.post(
        "/mcp",
        headers=ADMIN,
        json=rpc_request(
            "tools/call",
            {"name": "admin_reset_key", "arguments": {}}
        )
    )

    assert response.json()["result"]["isError"] is False
    assert len(downstream) == 1


def test_viewer_can_call_normal_tool(downstream):
    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=rpc_request(
            "tools/call",
            {
                "name": "get_customer_record",
                "arguments": {"customer_id": "CUST-12345"}
            }
        )
    )

    assert "result" in response.json()
    assert len(downstream) == 1


def test_tools_list_forwarded_unchanged(downstream):
    payload = rpc_request("tools/list", request_id=42)

    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=payload
    )

    assert response.status_code == 200
    assert downstream == [payload]
    assert response.json()["id"] == 42


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer invalid-token"},
        {"Authorization": "Basic credentials"},
    ]
)
def test_invalid_authentication(headers, downstream):
    response = client.post(
        "/mcp",
        headers=headers,
        json=rpc_request("tools/list")
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == -32001
    assert len(downstream) == 0


def test_missing_tool_name(downstream):
    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=rpc_request(
            "tools/call",
            {"arguments": {}}
        )
    )

    assert response.json()["error"]["code"] == -32602
    assert len(downstream) == 0


def test_malformed_json(downstream):
    response = client.post(
        "/mcp",
        headers={
            **VIEWER,
            "Content-Type": "application/json"
        },
        content="{not valid json"
    )

    assert response.json()["error"]["code"] == -32700
    assert len(downstream) == 0


def test_batch_rejected(downstream):
    batch = [
        rpc_request("tools/list"),
        rpc_request(
            "tools/call",
            {"name": "admin_reset_key"}
        )
    ]

    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=batch
    )

    assert response.json()["error"]["code"] == -32600
    assert len(downstream) == 0


def test_invalid_jsonrpc_version(downstream):
    payload = rpc_request("tools/list")
    payload["jsonrpc"] = "1.0"

    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=payload
    )

    assert response.json()["error"]["code"] == -32600
    assert len(downstream) == 0


def test_upstream_timeout_is_sanitized(monkeypatch):
    original_client = httpx.AsyncClient

    def timeout_handler(request):
        raise httpx.ReadTimeout("private upstream detail")

    transport = httpx.MockTransport(timeout_handler)

    def mock_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(gateway.httpx, "AsyncClient", mock_client)

    response = client.post(
        "/mcp",
        headers=VIEWER,
        json=rpc_request("tools/list")
    )

    body = response.json()

    assert body["error"]["code"] == -32002
    assert "private upstream detail" not in str(body)


@pytest.mark.parametrize("request_id", [True, [], {}])
def test_invalid_request_id_is_not_forwarded(downstream, request_id):
    response = client.post("/mcp", headers=VIEWER,
                           json=rpc_request("tools/list", request_id=request_id))
    assert response.json()["error"]["code"] == -32600
    assert response.json()["id"] is None
    assert downstream == []


def test_scalar_params_are_not_forwarded(downstream):
    response = client.post("/mcp", headers=VIEWER,
                           json=rpc_request("tools/list", params="invalid"))
    assert response.json()["error"]["code"] == -32602
    assert downstream == []
