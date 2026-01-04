"""
Polymarket API - Prix et Ordres
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# URLs
GAMMA_URL = "https://gamma-api.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


# ============ PROFIL ============

def resolve_username(username):
    """Résout un username en wallet address. Retourne (wallet, display_name) ou (None, None)"""
    try:
        r = requests.get(
            f"{GAMMA_URL}/public-search",
            params={"q": username, "search_profiles": "true"},
            timeout=10
        )
        if r.status_code != 200:
            return None, None
        
        profiles = r.json().get("profiles", [])
        if not profiles:
            return None, None
        
        # Cherche correspondance exacte ou prend le premier
        for p in profiles:
            if p.get("name", "").lower() == username.lower():
                return p.get("proxyWallet"), p.get("name") or p.get("pseudonym")
        
        # Sinon premier résultat
        p = profiles[0]
        return p.get("proxyWallet"), p.get("name") or p.get("pseudonym")
    except:
        return None, None


def resolve_users(usernames):
    """Résout une liste de usernames. Retourne {wallet: display_name}"""
    resolved = {}
    for username in usernames:
        wallet, name = resolve_username(username)
        if wallet:
            resolved[wallet.lower()] = name
            print(f"  ✅ @{username} → {wallet[:12]}...")
        else:
            print(f"  ❌ @{username} not found")
    return resolved


def resolve_wallets(wallets):
    """Résout une liste de wallets. Retourne {wallet: display_name}"""
    resolved = {}
    for wallet in wallets:
        wallet = wallet.lower()
        try:
            r = requests.get(f"{GAMMA_URL}/public-profile", params={"address": wallet}, timeout=10)
            if r.status_code == 200:
                p = r.json()
                name = p.get("name") or p.get("pseudonym") or wallet[:12]
                resolved[wallet] = name
                print(f"  ✅ {wallet[:12]}... → @{name}")
            else:
                resolved[wallet] = wallet[:12]
                print(f"  ⚠️ {wallet[:12]}... (no profile)")
        except:
            resolved[wallet] = wallet[:12]
            print(f"  ⚠️ {wallet[:12]}... (error)")
    return resolved


# ============ PRIX ============

def get_price(token_id):
    """Récupère bid/ask/mid pour un token"""
    result = {"bid": 0, "ask": 0, "mid": 0}
    
    try:
        r = requests.get(f"{CLOB_API_URL}/price", params={"token_id": token_id, "side": "SELL"}, timeout=5)
        if r.status_code == 200:
            result["bid"] = float(r.json().get("price", 0))
    except:
        pass
    
    try:
        r = requests.get(f"{CLOB_API_URL}/price", params={"token_id": token_id, "side": "BUY"}, timeout=5)
        if r.status_code == 200:
            result["ask"] = float(r.json().get("price", 0))
    except:
        pass
    
    try:
        r = requests.get(f"{CLOB_API_URL}/midpoint", params={"token_id": token_id}, timeout=5)
        if r.status_code == 200:
            result["mid"] = float(r.json().get("mid", 0))
    except:
        pass
    
    # Fallbacks
    if result["bid"] == 0 and result["ask"] == 0 and result["mid"] > 0:
        result["bid"] = result["mid"] - 0.005
        result["ask"] = result["mid"] + 0.005
    if result["mid"] == 0 and result["bid"] > 0 and result["ask"] > 0:
        result["mid"] = (result["bid"] + result["ask"]) / 2
    
    return result


def get_execution_price(token_id, side):
    """Retourne le prix d'exécution pour un side (BUY/SELL)"""
    prices = get_price(token_id)
    if side == "BUY":
        return prices["ask"]
    else:
        return prices["bid"]


# ============ ACTIVITÉ ============

def get_trades(wallet, limit=20):
    """Récupère les trades récents d'un wallet"""
    try:
        r = requests.get(
            f"{DATA_API_URL}/activity",
            params={"user": wallet, "type": "TRADE", "limit": limit, "sortBy": "TIMESTAMP", "sortDirection": "DESC"},
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []


def get_positions(wallet):
    """Récupère les positions ouvertes d'un wallet"""
    try:
        r = requests.get(f"{DATA_API_URL}/positions", params={"user": wallet}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []


def get_wallet_value(wallet):
    """Calcule la valeur totale d'un wallet (positions + USDC on-chain)"""
    wallet = wallet.lower()
    # Positions Polymarket
    try:
        r = requests.get(f"{DATA_API_URL}/positions", params={"user": wallet, "sizeThreshold": 0.01}, timeout=10)
        positions_value = sum(float(p.get("currentValue", 0)) for p in r.json()) if r.status_code == 200 else 0
    except:
        positions_value = 0
    # USDC on-chain
    try:
        usdc_contract = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
        data = "0x70a08231" + wallet[2:].zfill(64)
        r = requests.post("https://polygon-rpc.com", json={"jsonrpc": "2.0", "method": "eth_call", "params": [{"to": usdc_contract, "data": data}, "latest"], "id": 1}, timeout=10)
        usdc_balance = int(r.json().get("result", "0x0"), 16) / 1e6
    except:
        usdc_balance = 0
    return positions_value + usdc_balance


# ============ ORDRES LIVE ============

def get_client():
    """Crée un client CLOB authentifié"""
    from py_clob_client.client import ClobClient
    
    key = os.getenv("POLYMARKET_PRIVATE_KEY")
    if not key:
        raise ValueError("POLYMARKET_PRIVATE_KEY not set in .env")
    
    signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
    funder = os.getenv("POLYMARKET_FUNDER")
    
    if funder:
        client = ClobClient(HOST, key=key, chain_id=CHAIN_ID, signature_type=signature_type, funder=funder)
    else:
        client = ClobClient(HOST, key=key, chain_id=CHAIN_ID)
    
    client.set_api_creds(client.create_or_derive_api_creds())
    return client


def place_market_order(token_id, side, usd_amount, max_retries=3):
    """Place un ordre market FOK"""
    from py_clob_client.clob_types import MarketOrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY, SELL
    
    order_side = BUY if side == "BUY" else SELL
    
    for attempt in range(max_retries):
        try:
            client = get_client()
            args = MarketOrderArgs(
                token_id=token_id,
                amount=usd_amount,
                side=order_side,
                order_type=OrderType.FOK
            )
            signed = client.create_market_order(args)
            resp = client.post_order(signed, OrderType.FOK)
            return {"success": True, "response": resp}
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ Order attempt {attempt+1} failed: {e}, retrying...")
                time.sleep(1)
            else:
                return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "Max retries exceeded"}


# ============ UTILS ============

def calc_slippage(original_price, execution_price, side):
    """Calcule le slippage en %"""
    if original_price == 0:
        return 0
    if side == "BUY":
        return (execution_price - original_price) / original_price
    else:
        return (original_price - execution_price) / original_price