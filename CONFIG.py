# ============ COPYTRADING CONFIG ============

# Mode: "debug" (simulation) ou "live" (ordres réels)
MODE = "live"

# Wallets à copier: (wallet, montant_alloué)
TARGET_WALLETS = [
    ("0x000d257d2dc7616feaef4ae0f14600fdf50a758e", 1000),
]

# Exécution
MAX_SLIPPAGE = 0.05  # 5% max, sinon skip
MIN_PRICE = 0.01 # prix mini d'achat
MAX_PRICE = 0.99 # prix max d'achat
POLL_INTERVAL = 3.0

# Fichier de sauvegarde
SAVE_FILE = "copytrading_state.json"