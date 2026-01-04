"""
Polymarket Wallet Value
Calcule la valeur totale d'un wallet (positions + USDC on-chain)
"""
import requests

# ------ CONFIG ------
WALLET = '0x6031b6eed1c97e853c6e0f03ad3ce3529351f96d'
# --------------------

DATA_API = "https://data-api.polymarket.com"
USDC_CONTRACT = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"  # USDC on Polygon


def get_positions_value(wallet):
    """Récupère la valeur des positions Polymarket"""
    r = requests.get(f"{DATA_API}/positions", params={"user": wallet, "sizeThreshold": 0.01}, timeout=10)
    r.raise_for_status()
    positions = r.json()
    total = sum(float(p.get("currentValue", 0)) for p in positions)
    return total, len(positions)


def get_usdc_balance(wallet):
    """Récupère le solde USDC via RPC Polygon"""
    # balanceOf(address) selector = 0x70a08231
    data = "0x70a08231" + wallet[2:].lower().zfill(64)
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [{"to": USDC_CONTRACT, "data": data}, "latest"],
        "id": 1
    }
    r = requests.post("https://polygon-rpc.com", json=payload, timeout=10)
    r.raise_for_status()
    result = r.json().get("result", "0x0")
    balance = int(result, 16) / 1e6  # USDC has 6 decimals
    return balance


def main():
    wallet = WALLET.lower()
    print(f"Wallet: {wallet}\n")

    positions_value, num_positions = get_positions_value(wallet)
    print(f"Positions ({num_positions}): ${positions_value:,.2f}")

    usdc_balance = get_usdc_balance(wallet)
    print(f"USDC on-chain:    ${usdc_balance:,.2f}")

    total = positions_value + usdc_balance
    print(f"\nTotal:            ${total:,.2f}")


if __name__ == "__main__":
    main()
