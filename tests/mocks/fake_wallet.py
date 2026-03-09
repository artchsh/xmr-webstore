from __future__ import annotations

from typing import Any

from common.wallet_rpc import IncomingTransfer, WalletRPCError


class FakeWalletRPC:
    instances: list["FakeWalletRPC"] = []

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
        self.username = username
        self.password = password
        self.wallet_file = wallet_file
        self.wallet_password = wallet_password
        self.wallet_auto_create = wallet_auto_create
        self.daemon_nodes = daemon_nodes or []
        self.wallet_create_language = wallet_create_language
        self.timeout_seconds = timeout_seconds

        self.closed = False
        self.raise_on_create_subaddress = False
        self.raise_on_get_balance = False
        self.raise_on_get_address = False

        self._next_subaddress_index = 0
        self.created_labels: list[str] = []
        self.subaddress_queue: list[dict[str, Any]] = []

        self.balance: dict[str, Any] = {"balance": 0, "unlocked_balance": 0}
        self.addresses: dict[str, Any] = {"address": "48FakePrimaryAddress"}
        self.incoming_transfers: dict[int, list[IncomingTransfer | dict[str, Any]]] = {}

        self.__class__.instances.append(self)

    async def close(self) -> None:
        self.closed = True

    async def ensure_wallet_ready(self) -> None:
        return None

    async def create_subaddress(self, label: str) -> dict[str, Any]:
        if self.raise_on_create_subaddress:
            raise WalletRPCError("wallet unavailable")

        self.created_labels.append(label)

        if self.subaddress_queue:
            return self.subaddress_queue.pop(0)

        index = self._next_subaddress_index
        self._next_subaddress_index += 1
        return {
            "address": f"84FakeSubAddress{index:05d}",
            "address_index": index,
        }

    async def get_balance(self) -> dict[str, Any]:
        if self.raise_on_get_balance:
            raise WalletRPCError("mocked wallet balance failure")
        return self.balance

    async def get_address(self) -> dict[str, Any]:
        if self.raise_on_get_address:
            raise WalletRPCError("mocked wallet address failure")
        return self.addresses

    async def get_incoming_transfers(
        self, subaddress_index: int
    ) -> list[IncomingTransfer]:
        rows = self.incoming_transfers.get(subaddress_index, [])
        parsed: list[IncomingTransfer] = []
        for row in rows:
            if isinstance(row, IncomingTransfer):
                parsed.append(row)
            else:
                parsed.append(
                    IncomingTransfer(
                        amount=int(row.get("amount", 0)),
                        confirmations=int(row.get("confirmations", 0)),
                        txid=str(row.get("txid", "")),
                    )
                )
        return parsed
