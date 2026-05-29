"""
ARKK Put Strategy Engine v2
============================
Corrected implementation with:
- Budget constraints (cannot spend more than reserve)
- Proper expiration tracking and calendar rolls
- Progressive profit taking (2x, between 2x-3x, 3x milestones)
- Reload mechanics with regime awareness
- Proper position value lookups across expirations
"""

import os
import csv
import numpy as np
from data_loader import OptionsData

# ============================================================
# STRATEGY PARAMETERS (to be optimized later)
# ============================================================
TOTAL_BUDGET = 100000
TARGET_POSITION_VALUE = 20000
MODERATE_OTM_PCT = 0.22
DEEP_OTM_PCT = 0.37
MODERATE_ALLOC_PCT = 0.40
DEEP_ALLOC_PCT = 0.60

ROLL_TRIGGER_PCT = 0.30          # Roll at 30% drawdown from cost basis
PROFIT_TAKE_1_MULT = 2.0         # First milestone: 2x
PROFIT_TAKE_1_TRIM = 0.50        # Trim 50% at 2x
PROFIT_TAKE_2_MULT = 3.0         # Second milestone: 3x
PROFIT_TAKE_2_TRIM = 0.50        # Trim 50% at 3x
BETWEEN_MILESTONE_TRIM = True    # Enable proportional trimming between milestones
RELOAD_TRIGGER_PCT = 0.30        # Reload at 30% drawdown from exit prices
RELOAD_PARTIAL_PCT = 0.25        # Partial reload at 25%
CALENDAR_ROLL_THETA_RATIO = 1.5  # Roll when current theta >= 1.5x next expiry


class Position:
    def __init__(self, strike, contracts, cost_per, expiration, entry_date):
        self.strike = strike
        self.contracts = contracts
        self.cost_per = cost_per
        self.expiration = expiration
        self.entry_date = entry_date
    
    def cost_basis(self):
        return self.cost_per * self.contracts * 100
    
    def __repr__(self):
        return f"{self.contracts}x${self.strike}p @${self.cost_per:.2f} [{self.expiration}]"


class Strategy:
    def __init__(self, data):
        self.data = data
        self.reserve = TOTAL_BUDGET
        self.positions = []
        self.cum_realized = 0.0
        self.transactions = []
        self.snapshots = []
        
        # State tracking
        self.current_expiration = None
        self.milestone_reached = 0       # 0=none, 1=hit 2x, 2=hit 3x
        self.last_exit_prices = {}       # {strike: price} from last profit take
        self.awaiting_reload = False
        self.partial_reload_done = False
        self.peak_multiple = 0.0         # Track highest multiple for between-milestone trimming
        self.total_trimmed_between = 0.0 # Track how much trimmed between milestones
    
    # ============================================================
    # HELPERS
    # ============================================================
    
    def total_cost_basis(self):
        return sum(p.cost_basis() for p in self.positions)
    
    def position_value(self, date_str):
        total = 0
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if opt and opt['bid'] is not None and not np.isnan(opt['bid']):
                mid = opt['mid'] if (opt['mid'] is not None and not np.isnan(opt['mid'])) else opt['bid']
                total += mid * p.contracts * 100
        return round(total, 2)
    
    def current_multiple(self, date_str):
        cb = self.total_cost_basis()
        if cb <= 0:
            return 0
        return self.position_value(date_str) / cb
    
    def can_afford(self, amount):
        return self.reserve >= amount
    
    def log(self, date_str, action, details, realized=0):
        self.transactions.append({
            'date': date_str, 'action': action, 'details': details,
            'realized_pnl': round(realized, 2),
            'cum_realized': round(self.cum_realized, 2),
            'reserve': round(self.reserve, 2),
            'position_value': self.position_value(date_str) if self.positions else 0
        })
    
    def snapshot(self, date_str, action="HOLD"):
        arkk = self.data.get_underlying_price(date_str)
        pv = self.position_value(date_str) if self.positions else 0
        cb = self.total_cost_basis()
        self.snapshots.append({
            'date': date_str,
            'arkk': arkk,
            'position_value': pv,
            'cost_basis': round(cb, 2),
            'cum_realized': round(self.cum_realized, 2),
            'net_pl': round(self.cum_realized + pv - cb, 2),
            'reserve': round(self.reserve, 2),
            'n_contracts': sum(p.contracts for p in self.positions),
            'action': action
        })
    
    # ============================================================
    # ENTRY
    # ============================================================
    
    def enter_positions(self, date_str, deploy_amount, expiration):
        price = self.data.get_underlying_price(date_str)
        if not price:
            return False
        
        if not self.can_afford(deploy_amount):
            deploy_amount = max(0, self.reserve - 500)  # keep $500 buffer
            if deploy_amount < 5000:
                print(f"    ⛔ Insufficient reserve (${self.reserve:,.0f}) — cannot enter")
                return False
        
        mod_strike_target = price * (1 - MODERATE_OTM_PCT)
        deep_strike_target = price * (1 - DEEP_OTM_PCT)
        
        mod_candidates = self.data.get_strikes_near(date_str, price, MODERATE_OTM_PCT, n=3)
        deep_candidates = self.data.get_strikes_near(date_str, price, DEEP_OTM_PCT, n=3)
        
        if not mod_candidates or not deep_candidates:
            print(f"    ⛔ No suitable strikes found")
            return False
        
        mod = mod_candidates[0]
        deep = deep_candidates[0]
        
        mod_ask = mod['ask'] if mod['ask'] else mod['mid']
        deep_ask = deep['ask'] if deep['ask'] else deep['mid']
        
        if not mod_ask or not deep_ask or mod_ask <= 0 or deep_ask <= 0:
            print(f"    ⛔ Invalid prices for entry")
            return False
        
        mod_alloc = deploy_amount * MODERATE_ALLOC_PCT
        deep_alloc = deploy_amount * DEEP_ALLOC_PCT
        
        mod_contracts = max(1, int(mod_alloc / (mod_ask * 100)))
        deep_contracts = max(1, int(deep_alloc / (deep_ask * 100)))
        
        total_cost = mod_contracts * mod_ask * 100 + deep_contracts * deep_ask * 100
        
        if total_cost > self.reserve:
            scale = self.reserve / total_cost * 0.95
            mod_contracts = max(1, int(mod_contracts * scale))
            deep_contracts = max(1, int(deep_contracts * scale))
            total_cost = mod_contracts * mod_ask * 100 + deep_contracts * deep_ask * 100
        
        self.positions.append(Position(mod['strike'], mod_contracts, mod_ask, expiration, date_str))
        self.positions.append(Position(deep['strike'], deep_contracts, deep_ask, expiration, date_str))
        self.reserve -= total_cost
        self.current_expiration = expiration
        
        detail = f"{mod_contracts}x${mod['strike']}p @${mod_ask:.2f} + {deep_contracts}x${deep['strike']}p @${deep_ask:.2f}"
        self.log(date_str, "ENTRY", detail)
        print(f"    ✅ ENTRY: {detail} | Cost: ${total_cost:,.0f} | Reserve: ${self.reserve:,.0f}")
        return True
    
    # ============================================================
    # ROLL (30% drawdown from cost)
    # ============================================================
    
    def check_roll(self, date_str):
        if not self.positions:
            return False
        pv = self.position_value(date_str)
        cb = self.total_cost_basis()
        if cb <= 0:
            return False
        return (1 - pv / cb) >= ROLL_TRIGGER_PCT
    
    def execute_roll(self, date_str, expiration):
        recovered = 0
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if opt and opt['bid'] and not np.isnan(opt['bid']):
                recovered += opt['bid'] * p.contracts * 100
        
        cb = self.total_cost_basis()
        loss = recovered - cb
        self.cum_realized += loss
        self.reserve += recovered
        
        old_pos = str(self.positions)
        self.positions = []
        self.awaiting_reload = False
        self.partial_reload_done = False
        self.last_exit_prices = {}
        self.milestone_reached = 0
        self.peak_multiple = 0
        self.total_trimmed_between = 0
        
        self.log(date_str, "ROLL_CLOSE", f"Recovered ${recovered:,.0f} from {old_pos[:80]}", loss)
        print(f"    🔄 ROLL: Recovered ${recovered:,.0f} | Loss: ${loss:,.0f} | Cum: ${self.cum_realized:,.0f}")
        
        return self.enter_positions(date_str, TARGET_POSITION_VALUE, expiration)
    
    # ============================================================
    # PROFIT TAKE (milestone-based)
    # ============================================================
    
    def check_profit_take(self, date_str):
        mult = self.current_multiple(date_str)
        
        if self.milestone_reached == 0 and mult >= (PROFIT_TAKE_1_MULT * 0.95):
            return 'milestone_1'
        if self.milestone_reached == 1 and mult >= (PROFIT_TAKE_2_MULT * 0.95):
            return 'milestone_2'
        return None
    
    def execute_profit_take(self, date_str, milestone):
        pv = self.position_value(date_str)
        
        if milestone == 'milestone_1':
            trim_pct = PROFIT_TAKE_1_TRIM
            self.milestone_reached = 1
        else:
            trim_pct = PROFIT_TAKE_2_TRIM
            self.milestone_reached = 2
        
        total_proceeds = 0
        total_cost_sold = 0
        details = []
        
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if not opt or not opt['bid']:
                continue
            
            bid = opt['bid']
            sell_qty = max(1, int(p.contracts * trim_pct + 0.5))
            sell_qty = min(sell_qty, p.contracts - 1)
            
            if sell_qty <= 0:
                continue
            
            proceeds = sell_qty * bid * 100
            cost_sold = sell_qty * p.cost_per * 100
            
            total_proceeds += proceeds
            total_cost_sold += cost_sold
            self.last_exit_prices[p.strike] = bid
            
            details.append(f"Sell {sell_qty}x${p.strike}p @${bid:.2f}")
            p.contracts -= sell_qty
        
        self.positions = [p for p in self.positions if p.contracts > 0]
        
        gain = total_proceeds - total_cost_sold
        self.cum_realized += gain
        self.reserve += total_proceeds
        self.awaiting_reload = True
        self.partial_reload_done = False
        self.peak_multiple = 0
        self.total_trimmed_between = 0
        
        detail = " | ".join(details)
        label = f"PROFIT_TAKE_{milestone[-1]}"
        self.log(date_str, label, detail, gain)
        print(f"    💰 {label}: Proceeds ${total_proceeds:,.0f} | Gain: ${gain:,.0f} | Cum: ${self.cum_realized:,.0f}")
    
    # ============================================================
    # BETWEEN-MILESTONE TRIMMING
    # ============================================================
    
    def check_between_trim(self, date_str):
        if not BETWEEN_MILESTONE_TRIM:
            return False
        if self.milestone_reached != 1:
            return False
        
        mult = self.current_multiple(date_str)
        
        if mult > self.peak_multiple:
            self.peak_multiple = mult
        
        if mult >= 2.2 and mult < (PROFIT_TAKE_2_MULT * 0.95):
            progress = (mult - PROFIT_TAKE_1_MULT) / (PROFIT_TAKE_2_MULT - PROFIT_TAKE_1_MULT)
            target_trim = progress * PROFIT_TAKE_2_TRIM
            if target_trim > self.total_trimmed_between + 0.05:
                return True
        return False
    
    def execute_between_trim(self, date_str):
        mult = self.current_multiple(date_str)
        progress = (mult - PROFIT_TAKE_1_MULT) / (PROFIT_TAKE_2_MULT - PROFIT_TAKE_1_MULT)
        trim_pct = min(0.15, progress * 0.10)
        
        total_proceeds = 0
        total_cost_sold = 0
        details = []
        
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if not opt or not opt['bid']:
                continue
            
            bid = opt['bid']
            sell_qty = max(1, int(p.contracts * trim_pct + 0.5))
            sell_qty = min(sell_qty, p.contracts - 1)
            
            if sell_qty <= 0:
                continue
            
            proceeds = sell_qty * bid * 100
            cost_sold = sell_qty * p.cost_per * 100
            total_proceeds += proceeds
            total_cost_sold += cost_sold
            self.last_exit_prices[p.strike] = bid
            details.append(f"Trim {sell_qty}x${p.strike}p @${bid:.2f}")
            p.contracts -= sell_qty
        
        self.positions = [p for p in self.positions if p.contracts > 0]
        
        gain = total_proceeds - total_cost_sold
        self.cum_realized += gain
        self.reserve += total_proceeds
        self.total_trimmed_between += trim_pct
        self.awaiting_reload = True
        
        detail = " | ".join(details)
        self.log(date_str, "BETWEEN_TRIM", detail, gain)
        print(f"    ✂️  BETWEEN TRIM ({mult:.2f}x): {detail} | Gain: ${gain:,.0f}")
    
    # ============================================================
    # RELOAD
    # ============================================================
    
    def check_reload(self, date_str):
        if not self.awaiting_reload or not self.last_exit_prices:
            return None
        
        # Check if this is sideways/decline (reload appropriate)
        # vs continued rally (roll might be better)
        pv = self.position_value(date_str)
        cb = self.total_cost_basis()
        
        if cb > 0 and (1 - pv / cb) >= ROLL_TRIGGER_PCT:
            return None  # Let the roll trigger handle this
        
        for p in self.positions:
            if p.strike in self.last_exit_prices:
                exit_px = self.last_exit_prices[p.strike]
                opt = self.data.get_option(date_str, p.strike, p.expiration)
                if opt and opt['mid'] is not None and not np.isnan(opt['mid']):
                    drawdown = 1 - opt['mid'] / exit_px
                    if not self.partial_reload_done and drawdown >= RELOAD_PARTIAL_PCT:
                        return 'partial'
                    if self.partial_reload_done and drawdown >= RELOAD_TRIGGER_PCT:
                        return 'full'
        return None
    
    def execute_reload(self, date_str, reload_type):
        pv = self.position_value(date_str)
        deficit = TARGET_POSITION_VALUE - pv
        
        if reload_type == 'partial':
            buy_amount = deficit * 0.5
        else:
            buy_amount = deficit
        
        if buy_amount <= 0 or not self.can_afford(buy_amount):
            buy_amount = min(buy_amount, self.reserve - 500)
            if buy_amount < 1000:
                print(f"    ⛔ Cannot reload — insufficient reserve")
                return
        
        details = []
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if not opt or not opt['ask']:
                continue
            
            ask = opt['ask']
            alloc = buy_amount / len(self.positions)
            new_qty = max(1, int(alloc / (ask * 100)))
            cost = new_qty * ask * 100
            
            if cost > self.reserve - 500:
                new_qty = max(1, int((self.reserve - 500) / (ask * 100)))
                cost = new_qty * ask * 100
            
            old_total = p.cost_per * p.contracts
            new_total = ask * new_qty
            p.cost_per = (old_total + new_total) / (p.contracts + new_qty)
            p.contracts += new_qty
            self.reserve -= cost
            details.append(f"Buy {new_qty}x${p.strike}p @${ask:.2f}")
        
        if reload_type == 'partial':
            self.partial_reload_done = True
        else:
            self.awaiting_reload = False
            self.partial_reload_done = False
        
        label = f"RELOAD_{'PARTIAL' if reload_type == 'partial' else 'FULL'}"
        detail = " | ".join(details)
        self.log(date_str, label, detail)
        print(f"    🔄 {label}: {detail} | Reserve: ${self.reserve:,.0f}")
    
    # ============================================================
    # CALENDAR ROLL
    # ============================================================
    
    def check_calendar_roll(self, date_str, next_exp):
        if not self.positions:
            return False
        
        for p in self.positions:
            cur = self.data.get_option(date_str, p.strike, p.expiration)
            nxt = self.data.get_option(date_str, p.strike, next_exp)
            
            if (cur and nxt and cur['theta'] and nxt['theta'] and
                abs(nxt['theta']) > 0):
                ratio = abs(cur['theta']) / abs(nxt['theta'])
                if ratio >= CALENDAR_ROLL_THETA_RATIO:
                    return True
        return False
    
    def execute_calendar_roll(self, date_str, new_exp):
        recovered = 0
        for p in self.positions:
            opt = self.data.get_option(date_str, p.strike, p.expiration)
            if opt and opt['bid'] and not np.isnan(opt['bid']):
                recovered += opt['bid'] * p.contracts * 100
        
        old_cb = self.total_cost_basis()
        realized = recovered - old_cb
        self.cum_realized += realized
        self.reserve += recovered
        
        old_positions = self.positions[:]
        self.positions = []
        
        deployed = 0
        for old_p in old_positions:
            opt_new = self.data.get_option(date_str, old_p.strike, new_exp)
            if opt_new and opt_new['ask'] and not np.isnan(opt_new['ask']):
                ask = opt_new['ask']
                cost = old_p.contracts * ask * 100
                if cost <= self.reserve - 500:
                    self.positions.append(Position(old_p.strike, old_p.contracts, ask, new_exp, date_str))
                    self.reserve -= cost
                    deployed += cost
                else:
                    new_qty = max(1, int((self.reserve - 500) / (ask * 100)))
                    cost = new_qty * ask * 100
                    self.positions.append(Position(old_p.strike, new_qty, ask, new_exp, date_str))
                    self.reserve -= cost
                    deployed += cost
        
        self.current_expiration = new_exp
        net = recovered - deployed
        
        self.log(date_str, "CALENDAR_ROLL", f"Recovered ${recovered:,.0f}, Deployed ${deployed:,.0f}", realized)
        print(f"    📅 CALENDAR ROLL to {new_exp}: Recovered ${recovered:,.0f} | Deployed ${deployed:,.0f} | Loss: ${realized:,.0f}")
    
    # ============================================================
    # MAIN LOOP
    # ============================================================
    
    def run(self):
        print("\n" + "=" * 70)
        print("ARKK SYNTHETIC SHORT — STRATEGY BACKTEST v2")
        print("=" * 70)
        
        dates = self.data.get_dates()
        jan22 = '2022-01-21'
        jul22 = '2022-07-16'
        active_exp = jan22
        
        for i, d in enumerate(dates):
            arkk = self.data.get_underlying_price(d)
            if not arkk:
                continue
            
            # === INITIAL ENTRY ===
            if i == 0:
                print(f"\n[{d}] ARKK: ${arkk:.2f}")
                self.enter_positions(d, TARGET_POSITION_VALUE, active_exp)
                self.snapshot(d, "ENTRY")
                continue
            
            pv = self.position_value(d)
            cb = self.total_cost_basis()
            mult = pv / cb if cb > 0 else 0
            
            print(f"\n[{d}] ARKK: ${arkk:.2f} | PV: ${pv:,.0f} | CB: ${cb:,.0f} | {mult:.2f}x | Res: ${self.reserve:,.0f} | Contracts: {sum(p.contracts for p in self.positions)}")
            
            # === PRIORITY 1: PROFIT TAKE ===
            pt = self.check_profit_take(d)
            if pt:
                self.execute_profit_take(d, pt)
                self.snapshot(d, f"PROFIT_TAKE_{pt[-1]}")
                continue
            
            # === PRIORITY 2: BETWEEN-MILESTONE TRIM ===
            if self.check_between_trim(d):
                self.execute_between_trim(d)
                self.snapshot(d, "BETWEEN_TRIM")
                continue
            
            # === PRIORITY 3: RELOAD ===
            reload = self.check_reload(d)
            if reload:
                self.execute_reload(d, reload)
                self.snapshot(d, f"RELOAD_{reload.upper()}")
                continue
            
            # === PRIORITY 4: CALENDAR ROLL (DTE-based) ===
            if active_exp == jan22 and d >= '2021-06-17':
            # Force switch to JUL 22 when JAN 22 has < 220 DTE
             self.execute_calendar_roll(d, jul22)
             active_exp = jul22
             self.snapshot(d, "CALENDAR_ROLL")
             continue
            
            # === PRIORITY 5: ROLL (30% drawdown) ===
            if self.check_roll(d):
                if self.reserve < 5000:
                    print(f"    ⛔ Reserve too low for roll (${self.reserve:,.0f})")
                    self.snapshot(d, "HOLD_NO_RESERVE")
                    continue
                self.execute_roll(d, active_exp)
                self.snapshot(d, "ROLL")
                continue
            
            # === NO ACTION ===
            self.snapshot(d, "HOLD")
        
        return self
    
    # ============================================================
    # RESULTS
    # ============================================================
    
    def print_results(self):
        print("\n" + "=" * 70)
        print("BACKTEST RESULTS")
        print("=" * 70)
        
        if not self.snapshots:
            return
        
        first, last = self.snapshots[0], self.snapshots[-1]
        
        print(f"\nPeriod: {first['date']} → {last['date']}")
        print(f"Budget: ${TOTAL_BUDGET:,}")
        print(f"Final Position Value: ${last['position_value']:,.0f}")
        print(f"Final Reserve: ${last['reserve']:,.0f}")
        print(f"Cum. Realized P/L: ${last['cum_realized']:,.0f}")
        print(f"Net P/L: ${last['net_pl']:,.0f}")
        print(f"Contracts: {last['n_contracts']}")
        
        actions = {}
        for t in self.transactions:
            actions[t['action']] = actions.get(t['action'], 0) + 1
        print(f"\nActions:")
        for a, c in sorted(actions.items()):
            print(f"  {a}: {c}")
        
        peak_pl = 0
        max_dd = 0
        for s in self.snapshots:
            if s['net_pl'] > peak_pl:
                peak_pl = s['net_pl']
            dd = s['net_pl'] - peak_pl
            if dd < max_dd:
                max_dd = dd
        print(f"\nMax Drawdown: ${max_dd:,.0f}")
        
        print("\n" + "-" * 70)
        print("TRANSACTION LOG")
        print("-" * 70)
        for t in self.transactions:
            pv = t.get('position_value', 0)
            print(f"  [{t['date']}] {t['action']:20s} | Real: ${t['realized_pnl']:>8,.0f} | Cum: ${t['cum_realized']:>9,.0f} | Res: ${t['reserve']:>9,.0f} | PV: ${pv:>8,.0f}")
            print(f"  {'':20s}   {t['details'][:90]}")
    
    def save_results(self):
        os.makedirs('output', exist_ok=True)
        
        with open('output/backtest_snapshots.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['date','arkk','position_value','cost_basis','cum_realized','net_pl','reserve','n_contracts','action'])
            w.writeheader()
            w.writerows(self.snapshots)
        
        with open('output/backtest_transactions.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['date','action','details','realized_pnl','cum_realized','reserve','position_value'])
            w.writeheader()
            w.writerows(self.transactions)
        
        print(f"\n✅ Saved to output/backtest_snapshots.csv")
        print(f"✅ Saved to output/backtest_transactions.csv")


if __name__ == '__main__':
    data = OptionsData()
    strategy = Strategy(data)
    strategy.run()
    strategy.print_results()
    strategy.save_results()