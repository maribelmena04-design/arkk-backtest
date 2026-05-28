# ARKK Synthetic Short Put Strategy — Configuration
# Derived from manual backtest simulation Oct 2020 - Dec 2021

# ============================================================
# POSITION SIZING
# ============================================================
TOTAL_BUDGET = 100000          # Total allocated capital for put program
TARGET_POSITION_VALUE = 20000  # Always maintain ~$20K in puts
INITIAL_DEPLOY_PCT = 0.20      # Deploy 20% of budget on entry

# ============================================================
# STRIKE SELECTION
# ============================================================
MODERATE_OTM_PCT = 0.22        # Moderate strike: ~22% OTM from current price
DEEP_OTM_PCT = 0.37            # Deep strike: ~37% OTM from current price
MODERATE_ALLOC_PCT = 0.40      # 40% of deployment to moderate strike
DEEP_ALLOC_PCT = 0.60          # 60% of deployment to deep strike

# ============================================================
# EXPIRATION SELECTION
# ============================================================
TARGET_DTE_MIN = 300           # Minimum 10 months to expiration
TARGET_DTE_MAX = 550           # Maximum ~18 months to expiration
CALENDAR_ROLL_DTE = 120        # Consider calendar roll when DTE < 4 months
# Calendar roll triggered when theta on current exp is >= 50% higher
# than theta on next available expiration at same strike

# ============================================================
# ROLL TRIGGERS (position losing value)
# ============================================================
ROLL_TRIGGER_PCT = 0.30        # Roll when position drops 30% from cost basis
# On roll: close all, realize loss, re-enter $20K at proportionally
# adjusted strikes from current underlying price
# Typical roll cost: ~$6,000

# ============================================================
# PROFIT TAKING (position gaining value)
# ============================================================
PROFIT_TAKE_MULTIPLE = 2.0     # Trim when position approximately doubles
PROFIT_TAKE_VARIANCE = 0.05   # Allow +-5% variance (trigger at ~1.9x-2.1x)
# On profit take: sell proportionally across strikes to bring
# position value back to ~$20K
# Proceeds go to reserve

# ============================================================
# RELOAD (after profit take, position declines)
# ============================================================
# Reload triggers ONLY after a profit take, not independently
RELOAD_PARTIAL_PCT = 0.25      # Buy half of needed amount at 25% drawdown
RELOAD_FULL_PCT = 0.30         # Complete restoration at 30% drawdown
# Drawdown measured from the PRICES at which contracts were sold
# during profit take, NOT from cost basis
# Buy enough to restore position to ~$20K

# ============================================================
# EXIT SIGNALS
# ============================================================
# Begin considering full exit when:
# - Intrinsic value >= 85-90% of total option value
# - This signals the move has largely played out
# - Remaining value is mostly synthetic short shares, not optionality
# Full exit: close everything, strategy complete

# ============================================================
# STRATEGY CYCLE
# ============================================================
# The self-funding cycle:
# Entry → [Roll if 30% drawdown] → Profit Take at 2x → 
# [Reload at 25-30% drawdown from exit prices] → Profit Take at 2x →
# [Reload] → ... → Exit when intrinsic dominates
#
# Each profit take returns ~$20K to reserve
# Each roll/reload costs ~$6K from reserve  
# One profit take funds ~3 rolls/reloads
# Strategy is self-sustaining as long as thesis produces periodic doubles
