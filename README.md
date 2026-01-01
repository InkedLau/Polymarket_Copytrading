# Polymarket Copytrading Bot

Copy trades from top Polymarket traders automatically.

## Features

- **Username-based tracking**: Just add usernames, wallets are resolved automatically
- **Real-time monitoring**: Polls for new trades every 3 seconds
- **Realistic execution**: Fetches live market prices, calculates slippage
- **Slippage protection**: Skips trades exceeding max slippage threshold
- **Flexible sizing**: Fixed amount, % of original trade, or % of portfolio
- **Debug mode**: Paper trading simulation before going live
- **Live mode**: Execute real orders via Polymarket CLOB API
- **State persistence**: Resumes after restart

## Installation

```bash
git clone https://github.com/youruser/polymarket-copytrading.git
cd polymarket-copytrading
pip install -r requirements.txt
```

## Configuration

### 1. Edit `CONFIG.py`

```python
# Mode: "debug" (simulation) or "live" (real orders)
MODE = "debug"

# Usernames to copy (without @)
TARGET_USERS = [
    "scottilicious",
    "gabagool22",
]

# Sizing
SIZING_MODE = "fixed"  # "fixed", "percent_of_trade", "percent_of_portfolio"
FIXED_SIZE = 10.0      # USD per trade (if fixed)

# Risk
MAX_SLIPPAGE = 0.05    # 5% max, skip trade if exceeded
```

### 2. For live trading, create `.env`

```bash
cp .env.example .env
```

Edit `.env` with your Polymarket credentials:

```
POLYMARKET_PRIVATE_KEY=your_private_key
POLYMARKET_FUNDER=your_funder_address
POLYMARKET_SIGNATURE_TYPE=0
```

## Usage

```bash
python monitor.py
```

### Output

```
🎮 POLYMARKET COPYTRADING - DEBUG MODE
============================================================

Resolving 2 users...
  ✅ @scottilicious → 0x6031b6eed1...
  ✅ @gabagool22 → 0x1a2b3c4d...

Tracking 2 traders:
  • @scottilicious (0x6031b6eed1...)
  • @gabagool22 (0x1a2b3c4d...)

Sizing: fixed ($10.00/trade)
Max slippage: 5.0%
Poll: 3.0s
============================================================

✅ Ready! Watching for trades...

🔔🔔🔔 TRADE DETECTED 🔔🔔🔔
   Trader: @scottilicious
   BUY 150.00 @ 0.6500 ($97.50)
   Bitcoin Up or Down - January 1, 5:45AM ET...
   Outcome: Up

   📥 Copying with $10.00...
      Original: 0.6500 → Exec: 0.6650 (slip: +2.31%)

   ✅ 🟡 SIM: BUY 15.04 @ 0.6650
```

## Project Structure

```
copytrading/
├── CONFIG.py              # Configuration
├── .env.example           # Credentials template
├── polymarket_trades.py   # API: prices, trades, orders
├── monitor.py             # Main monitoring script
├── requirements.txt       # Dependencies
└── copytrading_state.json # Saved state (auto-generated)
```

## How It Works

1. **Resolve usernames** → wallet addresses via Gamma API
2. **Poll activity** → check for new trades every N seconds
3. **Detect new trade** → compare timestamps, deduplicate
4. **Fetch live price** → get current bid/ask from CLOB API
5. **Calculate slippage** → compare to original trade price
6. **Execute** → simulate (debug) or place real order (live)
7. **Update state** → track positions, PnL, save to disk

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `gamma-api.polymarket.com/public-search` | Resolve username → wallet |
| `data-api.polymarket.com/activity` | Get recent trades |
| `clob.polymarket.com/price` | Get current bid/ask |
| `clob.polymarket.com/midpoint` | Get mid price |

## Sizing Modes

| Mode | Description |
|------|-------------|
| `fixed` | Fixed USD amount per trade |
| `percent_of_trade` | X% of the original trade size |
| `percent_of_portfolio` | X% of current portfolio value |

## Slippage Calculation

```
BUY:  slippage = (execution_price - original_price) / original_price
SELL: slippage = (original_price - execution_price) / original_price
```

Positive slippage = worse execution than the trader you're copying.

## State Persistence

State is saved to `copytrading_state.json` after each trade:
- Cash balance
- Open positions
- Trade history
- Statistics

The bot resumes from saved state on restart.

## Disclaimer

This software is for educational purposes. Trading involves risk. Past performance of copied traders does not guarantee future results. Use at your own risk.

## License

MIT