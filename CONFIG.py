# ============ COPYTRADING CONFIG ============

# Mode: "debug" (simulation) ou "live" (ordres réels)
MODE = "debug"

# Usernames à copier (sans le @)
TARGET_USERS = [
    # "scottilicious",
    "gabagool22",
]

# Capital initial (simulation)
INITIAL_CAPITAL = 1000.0

# Sizing
SIZING_MODE = "fixed"  # "fixed", "percent_of_trade", "percent_of_portfolio"
FIXED_SIZE = 10.0
PERCENT_OF_TRADE = 0.1
PERCENT_OF_PORTFOLIO = 0.02

# Exécution
MAX_SLIPPAGE = 0.05  # 5% max, sinon skip
MIN_PRICE = 0.01 # prix mini d'achat
MAX_PRICE = 0.99 # prix max d'achat
POLL_INTERVAL = 3.0

# Fichier de sauvegarde
SAVE_FILE = "copytrading_state.json"