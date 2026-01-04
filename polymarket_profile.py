"""
Polymarket Profile Monitor
Récupère les infos d'un profil et ses trades récents
"""
import requests
from datetime import datetime

# ------ CONFIG ------

# USERNAME = 'scottilicious'
USERNAME = 'gabagool22'

# --------------------



BASE_GAMMA = "https://gamma-api.polymarket.com"
BASE_DATA = "https://data-api.polymarket.com"


def search_profile(username: str) -> dict | None:
    """Recherche un profil par username"""
    url = f"{BASE_GAMMA}/public-search"
    params = {"q": username, "search_profiles": "true"}
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    
    profiles = resp.json().get("profiles", [])
    if not profiles:
        return None
    
    # Cherche correspondance exacte ou prend le premier
    for p in profiles:
        if p.get("name", "").lower() == username.lower():
            return p
    return profiles[0]


def get_profile_by_wallet(wallet: str) -> dict | None:
    """Récupère un profil par wallet address"""
    url = f"{BASE_GAMMA}/public-profile"
    params = {"address": wallet}
    resp = requests.get(url, params=params)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_recent_trades(wallet: str, limit: int = 20) -> list:
    """Récupère les trades récents d'un wallet"""
    url = f"{BASE_DATA}/activity"
    params = {
        "user": wallet,
        "type": "TRADE",
        "limit": limit,
        "sortBy": "TIMESTAMP",
        "sortDirection": "DESC"
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_positions(wallet: str, limit: int = 50) -> list:
    """Récupère les positions ouvertes"""
    url = f"{BASE_DATA}/positions"
    params = {
        "user": wallet,
        "sizeThreshold": 0.1,
        "limit": limit
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def format_timestamp(ts: int) -> str:
    """Convertit timestamp unix en datetime lisible"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def main():
    username = USERNAME
    
    # 1. Recherche du profil
    print(f"[1] Recherche du profil @{username}...")
    profile = search_profile(username)
    
    if not profile:
        print(f"    Profil non trouvé!")
        return
    
    wallet = profile.get("proxyWallet")
    name = profile.get("name") or profile.get("pseudonym")
    bio = profile.get("bio", "")
    
    print(f"    Nom: {name}")
    print(f"    Wallet: {wallet}")
    if bio:
        print(f"    Bio: {bio[:100]}")
    
    # 2. Trades récents
    print(f"\n[2] Derniers trades...")
    trades = get_recent_trades(wallet, limit=10)
    
    if not trades:
        print("    Aucun trade récent")
    else:
        for t in trades:
            side = t.get("side", "?")
            size = t.get("size", 0)
            price = t.get("price", 0)
            usdc = t.get("usdcSize", 0)
            title = t.get("title", "")[:50]
            outcome = t.get("outcome", "?")
            ts = t.get("timestamp", 0)
            
            print(f"\n    [{side:4}] {size:>10.1f} @ {price:.3f} = ${usdc:>8.1f}")
            print(f"           {title}... → {outcome}")
            print(f"           {format_timestamp(ts)}")
    
    # 3. Positions ouvertes
    print(f"\n[3] Positions ouvertes...")
    positions = get_positions(wallet, limit=10)
    
    if not positions:
        print("    Aucune position")
    else:
        total_value = 0
        total_pnl = 0
        
        for p in positions:
            title = p.get("title", "")[:45]
            outcome = p.get("outcome", "?")
            size = p.get("size", 0)
            avg_price = p.get("avgPrice", 0)
            cur_price = p.get("curPrice", 0)
            current_value = p.get("currentValue", 0)
            pnl = p.get("cashPnl", 0)
            pnl_pct = p.get("percentPnl", 0)
            
            total_value += current_value
            total_pnl += pnl
            
            print(f"\n    {title}...")
            print(f"        {outcome}: {size:,.0f} shares")
            print(f"        Avg: {avg_price:.3f} → Now: {cur_price:.3f}")
            print(f"        Value: ${current_value:,.0f} | PnL: ${pnl:+,.0f} ({pnl_pct:+.1f}%)")
        
        print(f"\n    ────────────────────────────────")
        print(f"    TOTAL: ${total_value:,.0f} | PnL: ${total_pnl:+,.0f}")
    
    # 4. Export wallet pour usage ultérieur
    print(f"\n[4] Info pour copytrading:")
    print(f"    PROXY_WALLET = \"{wallet}\"")


if __name__ == "__main__":
    main()