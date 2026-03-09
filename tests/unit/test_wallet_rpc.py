from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.wallet_rpc import IncomingTransfer, MoneroWalletRPC, WalletRPCError


pytestmark = [pytest.mark.unit]


@pytest.mark.asyncio
async def test_rpc_raises_wallet_error_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=False,
    )

    async def fake_post(*_args, **_kwargs):
        return SimpleNamespace(status_code=503, text="unavailable", json=lambda: {})

    monkeypatch.setattr(rpc._client, "post", fake_post)

    with pytest.raises(WalletRPCError, match="HTTP 503"):
        await rpc._rpc("get_balance")

    await rpc.close()


@pytest.mark.asyncio
async def test_ensure_wallet_ready_auto_create_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=True,
    )

    calls: list[str] = []

    async def fake_rpc(method: str, params=None):
        calls.append(method)
        if method == "open_wallet" and calls.count("open_wallet") == 1:
            raise WalletRPCError("Wallet RPC error -4: wallet not found")
        return {}

    monkeypatch.setattr(rpc, "_rpc", fake_rpc)

    await rpc.ensure_wallet_ready()

    assert calls == ["open_wallet", "create_wallet", "open_wallet"]
    assert rpc._wallet_ready is True
    await rpc.close()


@pytest.mark.asyncio
async def test_create_subaddress_calls_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=False,
    )

    rpc._wallet_ready = True

    async def fake_rpc(method: str, params=None):
        assert method == "create_address"
        assert params == {"account_index": 0, "label": "order-abc"}
        return {"address": "84fake", "address_index": 7}

    monkeypatch.setattr(rpc, "_rpc", fake_rpc)

    result = await rpc.create_subaddress("order-abc")
    assert result["address"] == "84fake"
    assert int(result["address_index"]) == 7
    await rpc.close()


@pytest.mark.asyncio
async def test_get_incoming_transfers_parses_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=False,
    )

    rpc._wallet_ready = True

    async def fake_rpc(method: str, params=None):
        assert method == "get_transfers"
        assert params["subaddr_indices"] == [3]
        return {
            "in": [
                {"amount": 100, "confirmations": 2, "txid": "tx-1"},
                {"amount": 250, "confirmations": 11, "txid": "tx-2"},
            ]
        }

    monkeypatch.setattr(rpc, "_rpc", fake_rpc)
    rows = await rpc.get_incoming_transfers(3)

    assert rows == [
        IncomingTransfer(amount=100, confirmations=2, txid="tx-1"),
        IncomingTransfer(amount=250, confirmations=11, txid="tx-2"),
    ]
    await rpc.close()


@pytest.mark.asyncio
async def test_ensure_wallet_ready_handles_already_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=False,
    )

    async def fake_rpc(method: str, params=None):
        if method == "open_wallet":
            raise WalletRPCError("Wallet already open")
        return {}

    monkeypatch.setattr(rpc, "_rpc", fake_rpc)
    await rpc.ensure_wallet_ready()
    assert rpc._wallet_ready is True
    await rpc.close()


@pytest.mark.asyncio
async def test_call_with_daemon_failover_switches_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc = MoneroWalletRPC(
        rpc_url="http://wallet/json_rpc",
        username="user",
        password="pass",
        wallet_file="store.wallet",
        wallet_password="wallet-pass",
        wallet_auto_create=False,
        daemon_nodes=["node-a:18089", "node-b:18089"],
    )
    rpc._wallet_ready = True

    calls: list[str] = []

    async def fake_rpc(method: str, params=None):
        calls.append(method)
        if method == "get_balance":
            if calls.count("get_balance") == 1:
                raise WalletRPCError("no connection to daemon")
            return {"balance": 100, "unlocked_balance": 100}
        if method == "set_daemon":
            return {}
        return {}

    monkeypatch.setattr(rpc, "_rpc", fake_rpc)
    result = await rpc.get_balance()

    assert result["balance"] == 100
    assert "set_daemon" in calls
    await rpc.close()
