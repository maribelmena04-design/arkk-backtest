"""
Strategy Sensitivity Sweep
============================
Runs the strategy engine across different roll trigger values
and compares against baseline strategies (full deploy, simple short).
Computes drawdown-adjusted metrics for each.

Run: python sensitivity_sweep.py
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sys
import os
import importlib
import copy

# We'll import and modify strategy parameters
from data_loader import OptionsData

def run_strategy_with_params(data, roll_pct, deploy_pct=0.20):
    """
    Run the strategy with a specific roll trigger percentage.
    deploy_pct: fraction of budget to deploy (0.20 = $20K of $100K)
    Returns snapshots DataFrame.
    """
    # Import strategy module fresh each time
    import strategy_engine as se
    importlib.reload(se)
    
    # Override parameters
    se.ROLL_TRIGGER_PCT = roll_pct
    se.TARGET_POSITION_VALUE = int(100000 * deploy_pct)
    
    strategy = se.Strategy(data)
    
    # Suppress print output
    import io
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        strategy.run()
    finally:
        sys.stdout = old_stdout
    
    return strategy

def compute_full_deploy_baseline(data):
    """
    Simulate spending ALL $100K on puts at entry, never rolling.
    Track portfolio value over time.
    """
    dates = data.get_dates()
    entry_date = dates[0]
    price = data.get_underlying_price(entry_date)
    
    # Buy puts at 22% OTM and 37% OTM with full budget
    mod_candidates = data.get_strikes_near(entry_date, price, 0.22, n=1)
    deep_candidates = data.get_strikes_near(entry_date, price, 0.37, n=1)
    
    if not mod_candidates or not deep_candidates:
        return None
    
    mod = mod_candidates[0]
    deep = deep_candidates[0]
    
    mod_ask = mod['ask'] or mod['mid']
    deep_ask = deep['ask'] or deep['mid']
    
    # Allocate 40/60
    mod_contracts = int(40000 / (mod_ask * 100))
    deep_contracts = int(60000 / (deep_ask * 100))
    total_cost = mod_contracts * mod_ask * 100 + deep_contracts * deep_ask * 100
    
    snapshots = []
    for d in dates:
        opt_mod = data.get_option(d, mod['strike'])
        opt_deep = data.get_option(d, deep['strike'])
        
        val = 0
        if opt_mod and opt_mod['mid']:
            val += opt_mod['mid'] * mod_contracts * 100
        if opt_deep and opt_deep['mid']:
            val += opt_deep['mid'] * deep_contracts * 100
        
        net_pl = val - total_cost
        arkk = data.get_underlying_price(d)
        
        snapshots.append({
            'date': d,
            'arkk': arkk,
            'total_portfolio': val,
            'net_pl': net_pl,
            'cost': total_cost
        })
    
    return pd.DataFrame(snapshots)

def compute_short_baseline(data):
    """Simulate simple short of $100K of ARKK shares."""
    dates = data.get_dates()
    entry_price = data.get_underlying_price(dates[0])
    shares = int(100000 / entry_price)
    initial_proceeds = shares * entry_price
    
    snapshots = []
    for d in dates:
        price = data.get_underlying_price(d)
        if price is None:
            continue
        equity = 100000 + (entry_price - price) * shares
        net_pl = equity - 100000
        snapshots.append({
            'date': d,
            'arkk': price,
            'total_portfolio': equity,
            'net_pl': net_pl
        })
    
    return pd.DataFrame(snapshots)

def metrics_from_snapshots(snaps_df, label):
    """Compute key metrics from a snapshots DataFrame."""
    if 'total_portfolio' not in snaps_df.columns:
        # Strategy engine format
        snaps_df = snaps_df.copy()
        snaps_df['total_portfolio'] = snaps_df['position_value'] + snaps_df['reserve']
        snaps_df['net_pl'] = snaps_df['net_pl'] if 'net_pl' in snaps_df.columns else snaps_df['total_portfolio'] - 100000
    
    portfolio = snaps_df['total_portfolio']
    net_pl = snaps_df['net_pl']
    
    # Returns
    total_return = (portfolio.iloc[-1] - 100000) / 100000
    
    # Max drawdown on total portfolio
    rolling_max = portfolio.cummax()
    drawdown = portfolio - rolling_max
    max_dd_pct = (drawdown / rolling_max).min()
    max_dd_dollar = drawdown.min()
    
    # Time underwater (weeks where net_pl < 0)
    underwater_weeks = (net_pl < 0).sum()
    total_weeks = len(net_pl)
    pct_underwater = underwater_weeks / total_weeks * 100
    
    # Weekly returns for Sharpe/Sortino
    weekly_ret = portfolio.pct_change().dropna()
    rf_weekly = 0.02 / 52
    
    if weekly_ret.std() > 0:
        sharpe = (weekly_ret.mean() - rf_weekly) / weekly_ret.std() * np.sqrt(52)
    else:
        sharpe = 0
    
    neg_ret = weekly_ret[weekly_ret < 0]
    if len(neg_ret) > 0 and neg_ret.std() > 0:
        sortino = (weekly_ret.mean() - rf_weekly) / neg_ret.std() * np.sqrt(52)
    else:
        sortino = 0
    
    # Calmar
    calmar = total_return / abs(max_dd_pct) if max_dd_pct != 0 else 0
    
    # Return per unit of max drawdown (dollar)
    return_per_dd = net_pl.iloc[-1] / abs(max_dd_dollar) if max_dd_dollar != 0 else 0
    
    return {
        'label': label,
        'total_return_pct': round(total_return * 100, 1),
        'final_value': int(portfolio.iloc[-1]),
        'max_dd_pct': round(max_dd_pct * 100, 1),
        'max_dd_dollar': int(max_dd_dollar),
        'sharpe': round(sharpe, 3),
        'sortino': round(sortino, 3),
        'calmar': round(calmar, 3),
        'return_per_dd': round(return_per_dd, 2),
        'pct_underwater': round(pct_underwater, 1),
        'underwater_weeks': int(underwater_weeks),
    }


def main():
    data = OptionsData()
    
    print("\n" + "=" * 90)
    print("SENSITIVITY SWEEP: ROLL TRIGGER vs DRAWDOWN-ADJUSTED RETURN")
    print("=" * 90)
    
    # Run baselines
    print("\nComputing baselines...")
    
    short_df = compute_short_baseline(data)
    short_metrics = metrics_from_snapshots(short_df, "Simple Short")
    
    full_df = compute_full_deploy_baseline(data)
    full_metrics = metrics_from_snapshots(full_df, "Full Deploy (no roll)") if full_df is not None else None
    
    # Run strategy at different roll triggers
    roll_triggers = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    strategy_results = []
    strategy_equity_curves = {}
    
    for rt in roll_triggers:
        label = str(int(rt * 100)) + "% Roll"
        print("Running " + label + "...")
        
        try:
            strategy = run_strategy_with_params(data, rt)
            snaps = pd.DataFrame(strategy.snapshots)
            snaps['total_portfolio'] = snaps['position_value'] + snaps['reserve']
            
            m = metrics_from_snapshots(snaps, label)
            
            # Add roll-specific stats
            n_rolls = len([t for t in strategy.transactions if t['action'] == 'ROLL_CLOSE'])
            roll_cost = sum(t['realized_pnl'] for t in strategy.transactions if t['action'] == 'ROLL_CLOSE')
            n_profits = len([t for t in strategy.transactions if 'PROFIT' in t['action'] or 'TRIM' in t['action']])
            profit_captured = sum(t['realized_pnl'] for t in strategy.transactions if 'PROFIT' in t['action'] or 'TRIM' in t['action'])
            
            m['n_rolls'] = n_rolls
            m['roll_cost'] = int(roll_cost)
            m['n_profits'] = n_profits
            m['profit_captured'] = int(profit_captured)
            m['net_roll_impact'] = int(roll_cost + profit_captured)
            
            strategy_results.append(m)
            strategy_equity_curves[label] = snaps
            
        except Exception as e:
            print("  Error: " + str(e))
    
    # Print comparison table
    print("\n" + "=" * 90)
    print("RESULTS COMPARISON")
    print("=" * 90)
    
    header = "Strategy".ljust(22) + "Return".rjust(8) + "Max DD%".rjust(8) + "Sharpe".rjust(8) + "Calmar".rjust(8) + "Ret/DD$".rjust(8) + "%Underwater".rjust(12) + "Rolls".rjust(7) + "RollCost".rjust(10) + "Profits".rjust(10)
    print(header)
    print("-" * 110)
    
    # Baselines
    for m in [short_metrics, full_metrics]:
        if m:
            print(m['label'].ljust(22) + 
                  (str(m['total_return_pct']) + '%').rjust(8) + 
                  (str(m['max_dd_pct']) + '%').rjust(8) + 
                  str(m['sharpe']).rjust(8) + 
                  str(m['calmar']).rjust(8) + 
                  str(m['return_per_dd']).rjust(8) + 
                  (str(m['pct_underwater']) + '%').rjust(12) +
                  "N/A".rjust(7) + "N/A".rjust(10) + "N/A".rjust(10))
    
    print("-" * 110)
    
    # Strategy variants
    for m in strategy_results:
        print(m['label'].ljust(22) + 
              (str(m['total_return_pct']) + '%').rjust(8) + 
              (str(m['max_dd_pct']) + '%').rjust(8) + 
              str(m['sharpe']).rjust(8) + 
              str(m['calmar']).rjust(8) + 
              str(m['return_per_dd']).rjust(8) + 
              (str(m['pct_underwater']) + '%').rjust(12) +
              str(m['n_rolls']).rjust(7) + 
              ('$' + str(m['roll_cost'])).rjust(10) + 
              ('$' + str(m['profit_captured'])).rjust(10))
    
    # Find optimal
    print("\n" + "=" * 90)
    print("OPTIMAL ROLL TRIGGER ANALYSIS")
    print("=" * 90)
    
    if strategy_results:
        best_sharpe = max(strategy_results, key=lambda x: x['sharpe'])
        best_calmar = max(strategy_results, key=lambda x: x['calmar'])
        best_return = max(strategy_results, key=lambda x: x['total_return_pct'])
        best_dd = max(strategy_results, key=lambda x: x['max_dd_pct'])  # least negative
        
        print("\nBest Sharpe:   " + best_sharpe['label'] + " (" + str(best_sharpe['sharpe']) + ")")
        print("Best Calmar:   " + best_calmar['label'] + " (" + str(best_calmar['calmar']) + ")")
        print("Best Return:   " + best_return['label'] + " (" + str(best_return['total_return_pct']) + "%)")
        print("Lowest DD:     " + best_dd['label'] + " (" + str(best_dd['max_dd_pct']) + "%)")
        
        # Cost of rolling analysis
        print("\nROLLING COST ANALYSIS:")
        print("-" * 60)
        for m in strategy_results:
            efficiency = 0
            if m['roll_cost'] != 0:
                efficiency = m['profit_captured'] / abs(m['roll_cost'])
            print("  " + m['label'] + ": " + str(m['n_rolls']) + " rolls costing $" + str(abs(m['roll_cost'])) + 
                  " | " + str(m['n_profits']) + " profits capturing $" + str(m['profit_captured']) +
                  " | Ratio: " + str(round(efficiency, 2)) + "x")
    
    # Generate comparison chart
    plt.rcParams.update({
        'figure.facecolor': '#0a0a0a', 'axes.facecolor': '#0f0f0f',
        'axes.edgecolor': '#333', 'axes.labelcolor': '#ccc',
        'text.color': '#ccc', 'xtick.color': '#888', 'ytick.color': '#888',
        'grid.color': '#1a1a1a', 'grid.linestyle': '--', 'grid.alpha': 0.5,
        'font.family': 'monospace', 'font.size': 9,
    })
    
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    
    colors = ['#ef4444', '#f59e0b', '#e8c547', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899']
    
    # Chart 1: Equity curves
    ax = axes[0][0]
    for i, (label, snaps) in enumerate(strategy_equity_curves.items()):
        dates = pd.to_datetime(snaps['date'])
        ax.plot(dates, snaps['total_portfolio'], color=colors[i % len(colors)], 
                linewidth=1.5, alpha=0.8, label=label)
    if short_df is not None:
        ax.plot(pd.to_datetime(short_df['date']), short_df['total_portfolio'], 
                color='#666', linewidth=1, linestyle='--', alpha=0.5, label='Short')
    ax.axhline(y=100000, color='#fff', linestyle=':', alpha=0.2)
    ax.set_title('EQUITY CURVES BY ROLL TRIGGER', fontsize=11, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Portfolio Value ($)')
    ax.legend(fontsize=7, loc='upper left')
    ax.grid(True)
    
    # Chart 2: Sharpe vs Roll Trigger
    ax = axes[0][1]
    triggers = [int(m['label'].replace('% Roll', '')) for m in strategy_results]
    sharpes = [m['sharpe'] for m in strategy_results]
    calmars = [m['calmar'] for m in strategy_results]
    
    ax.bar([t - 1 for t in triggers], sharpes, width=2, color='#3b82f6', alpha=0.7, label='Sharpe')
    ax.bar([t + 1 for t in triggers], calmars, width=2, color='#10b981', alpha=0.7, label='Calmar')
    ax.set_xlabel('Roll Trigger (%)')
    ax.set_title('SHARPE & CALMAR BY ROLL TRIGGER', fontsize=11, fontweight='bold', color='#e8c547')
    ax.legend(fontsize=8)
    ax.grid(True, axis='y')
    
    # Chart 3: Return vs Max Drawdown scatter
    ax = axes[1][0]
    for i, m in enumerate(strategy_results):
        ax.scatter(abs(m['max_dd_pct']), m['total_return_pct'], 
                  color=colors[i % len(colors)], s=100, zorder=5, edgecolors='white', linewidths=0.5)
        ax.annotate(m['label'], (abs(m['max_dd_pct']), m['total_return_pct']),
                   textcoords="offset points", xytext=(5, 5), fontsize=7, color=colors[i % len(colors)])
    if short_metrics:
        ax.scatter(abs(short_metrics['max_dd_pct']), short_metrics['total_return_pct'],
                  color='#666', s=80, marker='D', zorder=5)
        ax.annotate('Short', (abs(short_metrics['max_dd_pct']), short_metrics['total_return_pct']),
                   textcoords="offset points", xytext=(5, 5), fontsize=7, color='#666')
    ax.set_xlabel('Max Drawdown (%)')
    ax.set_ylabel('Total Return (%)')
    ax.set_title('RETURN vs DRAWDOWN FRONTIER', fontsize=11, fontweight='bold', color='#e8c547')
    ax.grid(True)
    
    # Chart 4: Roll cost vs profit captured
    ax = axes[1][1]
    roll_costs = [abs(m['roll_cost']) for m in strategy_results]
    profits = [m['profit_captured'] for m in strategy_results]
    labels = [m['label'] for m in strategy_results]
    
    x = range(len(labels))
    ax.bar([i - 0.15 for i in x], roll_costs, width=0.3, color='#ef4444', alpha=0.7, label='Roll Cost')
    ax.bar([i + 0.15 for i in x], profits, width=0.3, color='#10b981', alpha=0.7, label='Profit Captured')
    ax.set_xticks(list(x))
    ax.set_xticklabels([l.replace(' Roll', '%') for l in labels], fontsize=8)
    ax.set_title('ROLL COST vs PROFIT CAPTURED', fontsize=11, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Dollars ($)')
    ax.legend(fontsize=8)
    ax.grid(True, axis='y')
    
    plt.tight_layout()
    plt.savefig('output/sensitivity_sweep.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("\nChart saved to output/sensitivity_sweep.png")


if __name__ == '__main__':
    main()