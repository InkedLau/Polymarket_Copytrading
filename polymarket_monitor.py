"""
Polymarket Copytrading Monitor
"""
import json
import time
import requests
from datetime import datetime
from pathlib import Path

from CONFIG import (
    MODE, TARGET_WALLETS,
    MIN_PRICE, MAX_PRICE,
    MAX_SLIPPAGE, POLL_INTERVAL, SAVE_FILE
)
import polymarket_trades as pm


# ============ STATE ============

# Résolu au démarrage: {wallet: {"name": str, "allocated": float, "value": float}}
wallets = {}

state = {
    "positions": {},      # asset -> {size, avg_price, title, outcome}
    "realized_pnl": 0.0,
    "trades": [],         # historique
    "seen": set(),        # trade_ids déjà traités
    "last_ts": {},        # wallet -> dernier timestamp
}

stats = {
    "detected": 0,
    "copied": 0,
    "skipped_slippage": 0,
    "skipped_funds": 0,
    "skipped_price": 0,
    "total_slippage": 0.0,
}


# ============ SIZING ============

def calc_size(wallet, original_usdc):
    """Calcule le montant à investir basé sur le ratio allocated/wallet_value, arrondi à l'entier inférieur"""
    info = wallets.get(wallet)
    if not info or info["value"] <= 0:
        return 0
    ratio = info["allocated"] / info["value"]
    return int(original_usdc * ratio)


# ============ EXECUTION ============

def execute_trade(trade, usdc_amount):
    """Exécute un trade (simulation ou live)"""
    asset = trade["asset"]
    side = trade["side"]
    original_price = float(trade["price"])
    
    # Récupère prix actuel
    exec_price = pm.get_execution_price(asset, side)
    if exec_price == 0:
        stats["skipped_price"] += 1
        print(f"      ⏭️ SKIP: No price available")
        return None
    
    if exec_price > MAX_PRICE:
        stats["skipped_price"] += 1
        print(f"      ⏭️ SKIP: Price too high")
        return None
    
    if exec_price < MIN_PRICE:
        stats["skipped_price"] += 1
        print(f"      ⏭️ SKIP: Price too low")
        return None

    # Calcule slippage
    slippage = pm.calc_slippage(original_price, exec_price, side)
    print(f"      Original: {original_price:.4f} → Exec: {exec_price:.4f} (slip: {slippage*100:+.2f}%)")
    
    if slippage > MAX_SLIPPAGE:
        stats["skipped_slippage"] += 1
        print(f"      ⏭️ SKIP: Slippage {slippage*100:.1f}% > max {MAX_SLIPPAGE*100:.1f}%")
        return None
    
    # Exécute
    if MODE == "live":
        result = pm.place_market_order(asset, side, usdc_amount)
        if not result["success"]:
            print(f"      ❌ ORDER FAILED: {result['error']}")
            return None
        print(f"      ✅ LIVE ORDER: {result['response']}")
    
    # Update state
    shares = usdc_amount / exec_price
    
    if side == "BUY":
        state["cash"] -= usdc_amount
        
        if asset in state["positions"]:
            pos = state["positions"][asset]
            total_cost = pos["size"] * pos["avg_price"] + usdc_amount
            total_shares = pos["size"] + shares
            pos["avg_price"] = total_cost / total_shares
            pos["size"] = total_shares
        else:
            state["positions"][asset] = {
                "size": shares,
                "avg_price": exec_price,
                "title": trade.get("title", ""),
                "outcome": trade.get("outcome", ""),
            }
    else:
        if asset not in state["positions"]:
            print(f"      ⏭️ SKIP: No position to sell")
            return None
        
        pos = state["positions"][asset]
        shares = min(shares, pos["size"])
        actual_usdc = shares * exec_price
        
        cost_sold = shares * pos["avg_price"]
        state["realized_pnl"] += actual_usdc - cost_sold
        state["cash"] += actual_usdc
        
        pos["size"] -= shares
        if pos["size"] < 0.001:
            del state["positions"][asset]
    
    stats["copied"] += 1
    stats["total_slippage"] += abs(slippage)
    
    # Log trade
    executed = {
        "time": time.time(),
        "side": side,
        "shares": shares,
        "exec_price": exec_price,
        "orig_price": original_price,
        "slippage": slippage,
        "usdc": usdc_amount,
        "asset": asset,
        "title": trade.get("title", "")[:50],
    }
    state["trades"].append(executed)
    save_state()
    
    return executed


# ============ MONITORING ============

def process_trade(trade):
    """Traite un nouveau trade détecté"""
    stats["detected"] += 1
    wallet = trade["wallet"]
    info = wallets.get(wallet, {})

    print(f"\n{'🔔'*3} TRADE DETECTED {'🔔'*3}")
    print(f"   Trader: @{info.get('name', wallet[:12])}")
    print(f"   {trade['side']} {float(trade['size']):.2f} @ {float(trade['price']):.4f} (${float(trade['usdcSize']):.2f})")
    print(f"   {trade.get('title', '')[:55]}...")
    print(f"   Outcome: {trade.get('outcome')}")

    # Refresh wallet value
    info["value"] = pm.get_wallet_value(wallet)
    ratio = info["allocated"] / info["value"] if info["value"] > 0 else 0
    print(f"   Wallet: ${info['value']:,.0f} | Allocated: ${info['allocated']:,.0f} | Ratio: {ratio:.2%}")

    usdc = calc_size(wallet, float(trade["usdcSize"]))

    if usdc < 1:
        stats["skipped_funds"] += 1
        print(f"\n      ⏭️ SKIP: Amount too small (${usdc})")
        return

    print(f"\n   📥 Copying with ${usdc}...")
    result = execute_trade(trade, usdc)

    if result:
        mode_tag = "🔴 LIVE" if MODE == "live" else "🟡 SIM"
        print(f"\n   ✅ {mode_tag}: {result['side']} {result['shares']:.2f} @ {result['exec_price']:.4f}")


def poll_wallets():
    """Poll tous les wallets pour nouveaux trades"""
    for wallet in wallets:
        trades = pm.get_trades(wallet, limit=20)

        for t in trades:
            trade_id = f"{t.get('timestamp')}:{t.get('asset')}:{t.get('side')}"
            ts = t.get("timestamp", 0)

            if trade_id not in state["seen"] and ts > state["last_ts"].get(wallet, 0):
                state["seen"].add(trade_id)
                t["wallet"] = wallet
                process_trade(t)

        if trades:
            state["last_ts"][wallet] = max(state["last_ts"].get(wallet, 0), max(t.get("timestamp", 0) for t in trades))


# ============ STATUS ============

def print_status():
    """Affiche le status du portfolio"""
    avg_slip = (stats["total_slippage"] / stats["copied"]) if stats["copied"] > 0 else 0

    print(f"\n{'='*60}")
    print(f"📊 STATUS ({MODE.upper()} MODE)")
    print(f"{'='*60}")
    print(f"  Detected:      {stats['detected']}")
    print(f"  Copied:        {stats['copied']}")
    print(f"  Avg slippage:  {avg_slip*100:.2f}%")
    print(f"  Skipped:       {stats['skipped_slippage']} slip / {stats['skipped_funds']} funds / {stats['skipped_price']} price")
    print(f"{'='*60}\n")


# ============ PERSISTENCE ============

def save_state():
    """Sauvegarde l'état"""
    data = {
        "timestamp": time.time(),
        "mode": MODE,
        "trades": state["trades"][-100:],
        "stats": stats,
    }
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_state():
    """Charge l'état précédent"""
    if not Path(SAVE_FILE).exists():
        return False

    try:
        with open(SAVE_FILE) as f:
            data = json.load(f)

        state["trades"] = data.get("trades", [])

        for t in state["trades"]:
            state["seen"].add(f"{t.get('time')}:{t.get('asset')}:{t.get('side')}")

        for k, v in data.get("stats", {}).items():
            if k in stats:
                stats[k] = v

        print(f"✅ Loaded: {len(state['trades'])} trades history")
        return True
    except Exception as e:
        print(f"⚠️ Load failed: {e}")
        return False


# ============ MAIN ============

def main():
    global wallets

    print("=" * 60)
    print(f"🎮 POLYMARKET COPYTRADING - {MODE.upper()} MODE")
    print("=" * 60)

    if not TARGET_WALLETS:
        print("⚠️  Configure TARGET_WALLETS in CONFIG.py!")
        return

    # Résout wallets → {wallet: {name, allocated, value}}
    print(f"\nResolving {len(TARGET_WALLETS)} wallets...")
    for wallet_addr, allocated in TARGET_WALLETS:
        wallet = wallet_addr.lower()
        # Get profile name
        try:
            r = requests.get(f"https://gamma-api.polymarket.com/public-profile", params={"address": wallet}, timeout=10)
            if r.status_code == 200:
                p = r.json()
                name = p.get("name") or p.get("pseudonym") or wallet[:12]
            else:
                name = wallet[:12]
        except:
            name = wallet[:12]
        # Get wallet value
        value = pm.get_wallet_value(wallet)
        wallets[wallet] = {"name": name, "allocated": allocated, "value": value}
        ratio = allocated / value if value > 0 else 0
        print(f"  ✅ @{name}: ${value:,.0f} value, ${allocated:,.0f} allocated ({ratio:.1%})")

    if not wallets:
        print("❌ No valid wallets!")
        return

    print(f"\nMax slippage: {MAX_SLIPPAGE*100:.1f}%")
    print(f"Poll: {POLL_INTERVAL}s")
    print("=" * 60)

    load_state()

    # Init timestamps
    print("\n⏳ Initializing...")
    for wallet, info in wallets.items():
        trades = pm.get_trades(wallet, limit=10)
        if trades:
            state["last_ts"][wallet] = trades[0].get("timestamp", 0)
            for t in trades:
                state["seen"].add(f"{t.get('timestamp')}:{t.get('asset')}:{t.get('side')}")
            print(f"   @{info['name']} last: {datetime.fromtimestamp(state['last_ts'][wallet]).strftime('%H:%M:%S')}")

    print("\n✅ Ready! Watching for trades...\n")
    print_status()

    last_status = time.time()

    try:
        while True:
            poll_wallets()

            if time.time() - last_status > 120:
                print_status()
                last_status = time.time()

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n👋 Stopping...")
        print_status()
        save_state()
        print(f"State saved to {SAVE_FILE}")


if __name__ == "__main__":
    main()