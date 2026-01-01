"""
Polymarket Copytrading Monitor
"""
import json
import time
from datetime import datetime
from pathlib import Path

from CONFIG import (
    MODE, TARGET_USERS, INITIAL_CAPITAL,
    SIZING_MODE, FIXED_SIZE, PERCENT_OF_TRADE, PERCENT_OF_PORTFOLIO,
    MIN_PRICE, MAX_PRICE,
    MAX_SLIPPAGE, POLL_INTERVAL, SAVE_FILE
)
import polymarket_trades as pm


# ============ STATE ============

# Résolu au démarrage: {wallet: display_name}
wallets = {}

state = {
    "cash": INITIAL_CAPITAL,
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

def calc_size(original_usdc):
    """Calcule le montant à investir"""
    if SIZING_MODE == "fixed":
        return min(FIXED_SIZE, state["cash"])
    elif SIZING_MODE == "percent_of_trade":
        return min(original_usdc * PERCENT_OF_TRADE, state["cash"])
    elif SIZING_MODE == "percent_of_portfolio":
        total = state["cash"] + sum(p["size"] * p.get("current_price", p["avg_price"]) for p in state["positions"].values())
        return min(total * PERCENT_OF_PORTFOLIO, state["cash"])
    return 0


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
    
    trader = trade.get("trader", trade["wallet"][:12])
    print(f"\n{'🔔'*3} TRADE DETECTED {'🔔'*3}")
    print(f"   Trader: @{trader}")
    print(f"   {trade['side']} {float(trade['size']):.2f} @ {float(trade['price']):.4f} (${float(trade['usdcSize']):.2f})")
    print(f"   {trade.get('title', '')[:55]}...")
    print(f"   Outcome: {trade.get('outcome')}")
    
    usdc = calc_size(float(trade["usdcSize"]))
    
    if usdc < 0.5:
        stats["skipped_funds"] += 1
        print(f"\n      ⏭️ SKIP: Insufficient funds (${state['cash']:.2f})")
        return
    
    print(f"\n   📥 Copying with ${usdc:.2f}...")
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
                t["trader"] = wallets[wallet]  # Display name
                process_trade(t)
        
        if trades:
            state["last_ts"][wallet] = max(state["last_ts"].get(wallet, 0), max(t.get("timestamp", 0) for t in trades))


# ============ STATUS ============

def print_status():
    """Affiche le status du portfolio"""
    # Update prix positions
    for asset, pos in state["positions"].items():
        prices = pm.get_price(asset)
        pos["current_price"] = prices["mid"] if prices["mid"] > 0 else pos["avg_price"]
    
    positions_value = sum(p["size"] * p.get("current_price", p["avg_price"]) for p in state["positions"].values())
    total_value = state["cash"] + positions_value
    unrealized = sum(p["size"] * (p.get("current_price", p["avg_price"]) - p["avg_price"]) for p in state["positions"].values())
    total_pnl = state["realized_pnl"] + unrealized
    pnl_pct = (total_pnl / INITIAL_CAPITAL) * 100
    avg_slip = (stats["total_slippage"] / stats["copied"]) if stats["copied"] > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"📊 PORTFOLIO ({MODE.upper()} MODE)")
    print(f"{'='*60}")
    print(f"  Cash:          ${state['cash']:>10.2f}")
    print(f"  Positions:     ${positions_value:>10.2f}")
    print(f"  Total:         ${total_value:>10.2f}")
    print(f"  ────────────────────────────────")
    print(f"  PnL:           {'+' if total_pnl >= 0 else ''}${total_pnl:>9.2f} ({'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%)")
    print(f"  ────────────────────────────────")
    print(f"  Detected:      {stats['detected']}")
    print(f"  Copied:        {stats['copied']}")
    print(f"  Avg slippage:  {avg_slip*100:.2f}%")
    print(f"  Skipped:       {stats['skipped_slippage']} slip / {stats['skipped_funds']} funds / {stats['skipped_price']} price")
    
    if state["positions"]:
        print(f"\n  Positions ({len(state['positions'])}):")
        for asset, p in state["positions"].items():
            pnl = p["size"] * (p.get("current_price", p["avg_price"]) - p["avg_price"])
            print(f"    • {p['outcome']}: {p['size']:.2f} @ {p['avg_price']:.4f}")
            print(f"      {p['title'][:45]}...")
            print(f"      PnL: {'+' if pnl >= 0 else ''}${pnl:.2f}")
    
    print(f"{'='*60}\n")


# ============ PERSISTENCE ============

def save_state():
    """Sauvegarde l'état"""
    data = {
        "timestamp": time.time(),
        "mode": MODE,
        "cash": state["cash"],
        "realized_pnl": state["realized_pnl"],
        "positions": state["positions"],
        "trades": state["trades"][-100:],  # Garde les 100 derniers
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
        
        state["cash"] = data.get("cash", INITIAL_CAPITAL)
        state["realized_pnl"] = data.get("realized_pnl", 0)
        state["positions"] = data.get("positions", {})
        state["trades"] = data.get("trades", [])
        
        # Rebuild seen set
        for t in state["trades"]:
            state["seen"].add(f"{t.get('time')}:{t.get('asset')}:{t.get('side')}")
        
        for k, v in data.get("stats", {}).items():
            if k in stats:
                stats[k] = v
        
        print(f"✅ Loaded: ${state['cash']:.2f} cash, {len(state['positions'])} positions")
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
    
    if not TARGET_USERS:
        print("⚠️  Configure TARGET_USERS in CONFIG.py!")
        return
    
    # Résout usernames → wallets
    print(f"\nResolving {len(TARGET_USERS)} users...")
    wallets = pm.resolve_users(TARGET_USERS)
    
    if not wallets:
        print("❌ No valid users found!")
        return
    
    print(f"\nTracking {len(wallets)} traders:")
    for wallet, name in wallets.items():
        print(f"  • @{name} ({wallet[:12]}...)")
    
    print(f"\nSizing: {SIZING_MODE} ", end="")
    if SIZING_MODE == "fixed":
        print(f"(${FIXED_SIZE}/trade)")
    elif SIZING_MODE == "percent_of_trade":
        print(f"({PERCENT_OF_TRADE*100:.0f}% of original)")
    else:
        print(f"({PERCENT_OF_PORTFOLIO*100:.0f}% of portfolio)")
    
    print(f"Max slippage: {MAX_SLIPPAGE*100:.1f}%")
    print(f"Poll: {POLL_INTERVAL}s")
    print("=" * 60)
    
    load_state()
    
    # Init timestamps
    print("\n⏳ Initializing...")
    for wallet, name in wallets.items():
        trades = pm.get_trades(wallet, limit=10)
        if trades:
            state["last_ts"][wallet] = trades[0].get("timestamp", 0)
            for t in trades:
                state["seen"].add(f"{t.get('timestamp')}:{t.get('asset')}:{t.get('side')}")
            print(f"   @{name} last: {datetime.fromtimestamp(state['last_ts'][wallet]).strftime('%H:%M:%S')}")
    
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