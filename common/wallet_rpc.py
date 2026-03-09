from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


class WalletRPCError(Exception):
    pass


@dataclass
class IncomingTransfer:
    amount: int
    confirmations: int
    txid: str


class MoneroWalletRPC:
    def __init__(
        self,
        rpc_url: str,
        username: str,
        password: str,
        wallet_file: str,
        wallet_password: str,
        wallet_auto_create: bool,
        daemon_nodes: list[str] | None = None,
        wallet_create_language: str = "English",
        timeout_seconds: int = 20,
    ) -> None:
        self.rpc_url = rpc_url
        self.wallet_file = wallet_file
        self.wallet_password = wallet_password
        self.wallet_auto_create = wallet_auto_create
        self.wallet_create_language = wallet_create_language
        self.daemon_nodes = [
            node.strip() for node in (daemon_nodes or []) if node.strip()
        ]
        self._active_daemon_index = -1
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            auth=httpx.DigestAuth(username, password),
        )
        self._rpc_id = 0
        self._wallet_ready = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_daemon_connection_error(exc: WalletRPCError) -> bool:
        text = str(exc).lower()
        return (
            "no connection to daemon" in text
            or "failed to connect to daemon" in text
            or "daemon is busy" in text
            or "daemon" in text
            and "connection" in text
        )

    async def _set_daemon(self, node: str) -> None:
        await self._rpc(
            "set_daemon",
            {
                "address": node,
                "trusted": True,
            },
        )

    async def _failover_daemon(self) -> bool:
        if not self.daemon_nodes:
            return False

        start = self._active_daemon_index
        total = len(self.daemon_nodes)

        for step in range(1, total + 1):
            idx = (start + step) % total
            node = self.daemon_nodes[idx]
            try:
                await self._set_daemon(node)
            except WalletRPCError:
                continue
            self._active_daemon_index = idx
            return True
        return False

    async def close(self) -> None:
        await self._client.aclose()

    async def _rpc(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._rpc_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": str(self._rpc_id),
            "method": method,
        }
        if params:
            payload["params"] = params

        try:
            response = await self._client.post(self.rpc_url, json=payload)
        except Exception as exc:
            raise WalletRPCError(f"Wallet RPC request failed: {exc}") from exc

        if response.status_code >= 400:
            raise WalletRPCError(
                f"Wallet RPC HTTP {response.status_code}: {response.text}"
            )

        data = response.json()
        if "error" in data:
            message = data["error"].get("message", "unknown wallet error")
            code = data["error"].get("code", "unknown")
            raise WalletRPCError(f"Wallet RPC error {code}: {message}")

        return data.get("result", {})

    async def ensure_wallet_ready(self) -> None:
        if self._wallet_ready:
            return

        async with self._lock:
            if self._wallet_ready:
                return

            try:
                await self._rpc(
                    "open_wallet",
                    {"filename": self.wallet_file, "password": self.wallet_password},
                )
            except WalletRPCError as exc:
                lowered = str(exc).lower()
                if "already open" in lowered or "wallet already opened" in lowered:
                    self._wallet_ready = True
                    return
                if not self.wallet_auto_create:
                    raise
                await self._rpc(
                    "create_wallet",
                    {
                        "filename": self.wallet_file,
                        "password": self.wallet_password,
                        "language": self.wallet_create_language,
                    },
                )
                await self._rpc(
                    "open_wallet",
                    {"filename": self.wallet_file, "password": self.wallet_password},
                )

            self._wallet_ready = True

            if self.daemon_nodes:
                if not await self._failover_daemon():
                    self._active_daemon_index = 0

    async def _call_with_daemon_failover(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return await self._rpc(method, params)
        except WalletRPCError as exc:
            if not self._is_daemon_connection_error(exc):
                raise
            switched = await self._failover_daemon()
            if not switched:
                raise
            return await self._rpc(method, params)

    async def create_subaddress(self, label: str) -> dict[str, Any]:
        await self.ensure_wallet_ready()
        return await self._call_with_daemon_failover(
            "create_address",
            {"account_index": 0, "label": label},
        )

    async def get_balance(self) -> dict[str, Any]:
        await self.ensure_wallet_ready()
        return await self._call_with_daemon_failover(
            "get_balance", {"account_index": 0}
        )

    async def get_address(self) -> dict[str, Any]:
        await self.ensure_wallet_ready()
        return await self._call_with_daemon_failover(
            "get_address", {"account_index": 0}
        )

    async def get_incoming_transfers(
        self, subaddress_index: int
    ) -> list[IncomingTransfer]:
        await self.ensure_wallet_ready()
        result = await self._call_with_daemon_failover(
            "get_transfers",
            {
                "in": True,
                "pool": True,
                "account_index": 0,
                "subaddr_indices": [subaddress_index],
            },
        )
        rows = result.get("in", []) or []
        transfers: list[IncomingTransfer] = []
        for item in rows:
            transfers.append(
                IncomingTransfer(
                    amount=int(item.get("amount", 0)),
                    confirmations=int(item.get("confirmations", 0)),
                    txid=str(item.get("txid", "")),
                )
            )
        return transfers
