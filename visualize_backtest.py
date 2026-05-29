"""
Backtest Results Visualization
===============================
Reads output/backtest_snapshots.csv and backtest_transactions.csv
to generate strategy performance charts.

Run: python visualize_backtest.py
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime
import os

plt.rcParams.update({
    'figure.facecolor': '#0a0a0a',
    'axes.facecolor': '#0f0f0f',
    'axes.edgecolor': '#333333',
    'axes.labelcolor': '#cccccc',
    'text.color': '#cccccc',
    'xtick.color': '#888888',
    'ytick.color': '#888888',
    'grid.color': '#1a1a1a',
    'grid.linestyle': '--',
    'grid.alpha': 0.5,
    'font.family': 'monospace',
    'font.size': 9,
})

ACTION_COLORS = {
    'ENTRY': '#3b82f6',
    'ROLL': '#f59e0b',
    'PROFIT_TAKE_1': '#10b981',
    'PROFIT_TAKE_2': '#10b981',
    'BETWEEN_TRIM': '#06b6d4',
    'RELOAD_PARTIAL': '#8b5cf6',
    'RELOAD_FULL': '#a855f7',
    'CALENDAR_ROLL': '#ec4899',
}

ACTION_MARKERS = {
    'ENTRY': 'v',
    'ROLL': 's',
    'PROFIT_TAKE_1': '^',
    'PROFIT_TAKE_2': 'D',
    'BETWEEN_TRIM': 'p',
    'RELOAD_PARTIAL': '<',
    'RELOAD_FULL': '>',
    'CALENDAR_ROLL': '*',
}

def load_data():
    snaps = pd.read_csv('output/backtest_snapshots.csv')
    snaps['date'] = pd.to_datetime(snaps['date'])
    txns = pd.read_csv('output/backtest_transactions.csv')
    txns['date'] = pd.to_datetime(txns['date'])
    return snaps, txns

def main():
    os.makedirs('output', exist_ok=True)
    snaps, txns = load_data()
    
    dates = snaps['date']
    arkk = snaps['arkk']
    pv = snaps['position_value']
    cb = snaps['cost_basis']
    cum_real = snaps['cum_realized']
    net_pl = snaps['net_pl']
    reserve = snaps['reserve']
    total_portfolio = pv + reserve
    n_contracts = snaps['n_contracts']
    actions = snaps['action']
    
    # Get action dates for markers
    action_dates = snaps[~snaps['action'].isin(['HOLD', 'HOLD_NO_RESERVE'])]
    
    # ================================================================
    # CHART 1: ARKK Price + All Strategy Actions
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.plot(dates, arkk, color='#3b82f6', linewidth=1.5, alpha=0.8, label='ARKK')
    ax.fill_between(dates, arkk, alpha=0.05, color='#3b82f6')
    
    plotted_labels = set()
    for _, row in action_dates.iterrows():
        action = row['action']
        color = ACTION_COLORS.get(action, '#ffffff')
        marker = ACTION_MARKERS.get(action, 'o')
        label = action if action not in plotted_labels else None
        plotted_labels.add(action)
        ax.scatter([row['date']], [row['arkk']], color=color, s=100, marker=marker,
                  zorder=5, edgecolors='white', linewidths=0.5, label=label)
    
    ax.set_title('ARKK PRICE ACTION — ALL STRATEGY EVENTS', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('ARKK Price ($)')
    ax.legend(loc='upper left', fontsize=7, ncol=2)
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_01_arkk_events.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("1/8 ARKK Price & Events")

    # ================================================================
    # CHART 2: Total Portfolio Value (Reserve + Position)
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.fill_between(dates, reserve, alpha=0.3, color='#3b82f6', label='Reserve')
    ax.fill_between(dates, reserve, total_portfolio, alpha=0.3, color='#e8c547', label='Position Value')
    ax.plot(dates, total_portfolio, color='#e8c547', linewidth=2, label='Total Portfolio')
    ax.axhline(y=100000, color='#ffffff', linestyle='--', alpha=0.2, linewidth=1)
    ax.text(dates.iloc[-1], 101500, 'Starting: $100K', color='#666', fontsize=7, ha='right')
    
    ax.set_title('TOTAL PORTFOLIO VALUE (Reserve + Position)', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Value ($)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_02_total_portfolio.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("2/8 Total Portfolio Value")
    
    # ================================================================
    # CHART 3: Net P/L Over Time
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    colors = ['#10b981' if v >= 0 else '#ef4444' for v in net_pl]
    ax.fill_between(dates, net_pl, 0,
                    where=net_pl >= 0, alpha=0.2, color='#10b981', interpolate=True)
    ax.fill_between(dates, net_pl, 0,
                    where=net_pl < 0, alpha=0.2, color='#ef4444', interpolate=True)
    ax.plot(dates, net_pl, color='#e8c547', linewidth=2)
    ax.axhline(y=0, color='#ffffff', linestyle='-', alpha=0.3, linewidth=1)
    
    # Mark key milestones
    for _, row in action_dates.iterrows():
        if row['action'] in ['PROFIT_TAKE_1', 'PROFIT_TAKE_2']:
            ax.annotate(row['action'].replace('PROFIT_TAKE_', 'PT'),
                       (row['date'], row['net_pl']),
                       textcoords="offset points", xytext=(0, 15),
                       ha='center', fontsize=7, color='#10b981', fontweight='bold')
    
    ax.set_title('NET P/L OVER TIME', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Net P/L ($)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_03_net_pl.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("3/8 Net P/L")

    # ================================================================
    # CHART 4: Position Value + Cost Basis
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.plot(dates, pv, color='#e8c547', linewidth=2, label='Position Value')
    ax.plot(dates, cb, color='#ef4444', linewidth=1, linestyle='--', alpha=0.6, label='Cost Basis')
    ax.axhline(y=20000, color='#3b82f6', linestyle=':', alpha=0.3, linewidth=1)
    ax.text(dates.iloc[0], 20800, 'Target: $20K', color='#3b82f6', fontsize=7)
    
    for _, row in action_dates.iterrows():
        action = row['action']
        if action in ACTION_COLORS:
            color = ACTION_COLORS[action]
            marker = ACTION_MARKERS.get(action, 'o')
            ax.scatter([row['date']], [row['position_value']], color=color, s=60,
                      marker=marker, zorder=5, edgecolors='white', linewidths=0.5)
    
    ax.set_title('POSITION VALUE vs COST BASIS', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Value ($)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_04_pv_vs_cb.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("4/8 Position Value vs Cost Basis")

    # ================================================================
    # CHART 5: Cumulative Realized P/L
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.fill_between(dates, cum_real, 0,
                    where=cum_real >= 0, alpha=0.2, color='#10b981', interpolate=True)
    ax.fill_between(dates, cum_real, 0,
                    where=cum_real < 0, alpha=0.2, color='#ef4444', interpolate=True)
    ax.plot(dates, cum_real, color='#10b981', linewidth=2)
    ax.axhline(y=0, color='#ffffff', linestyle='-', alpha=0.3, linewidth=1)
    
    # Annotate transactions
    for _, row in txns.iterrows():
        if row['realized_pnl'] != 0:
            color = '#10b981' if row['realized_pnl'] > 0 else '#ef4444'
            ax.scatter([row['date']], [row['cum_realized']], color=color, s=50, zorder=5,
                      edgecolors='white', linewidths=0.5)
    
    ax.set_title('CUMULATIVE REALIZED P/L', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Realized P/L ($)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_05_cum_realized.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("5/8 Cumulative Realized P/L")

    # ================================================================
    # CHART 6: Reserve Over Time
    # ================================================================
    fig, ax = plt.subplots(figsize=(16, 7))
    ax.plot(dates, reserve, color='#3b82f6', linewidth=2)
    ax.fill_between(dates, reserve, alpha=0.15, color='#3b82f6')
    ax.axhline(y=80000, color='#ffffff', linestyle='--', alpha=0.2, linewidth=1)
    ax.text(dates.iloc[-1], 81000, 'Starting Reserve: $80K', color='#666', fontsize=7, ha='right')
    
    for _, row in action_dates.iterrows():
        if row['action'] in ['ROLL', 'PROFIT_TAKE_1', 'PROFIT_TAKE_2', 'CALENDAR_ROLL']:
            ax.scatter([row['date']], [row['reserve']], 
                      color=ACTION_COLORS.get(row['action'], '#fff'), s=60,
                      marker=ACTION_MARKERS.get(row['action'], 'o'),
                      zorder=5, edgecolors='white', linewidths=0.5)
    
    ax.set_title('RESERVE BALANCE', fontsize=13, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Reserve ($)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_06_reserve.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("6/8 Reserve Balance")

    # ================================================================
    # CHART 7: ARKK Price vs Net P/L (Dual Axis)
    # ================================================================
    fig, ax1 = plt.subplots(figsize=(16, 7))
    ax2 = ax1.twinx()
    
    ax1.plot(dates, arkk, color='#3b82f6', linewidth=1.5, label='ARKK Price')
    ax2.plot(dates, net_pl, color='#e8c547', linewidth=2, label='Net P/L', linestyle='--')
    ax2.axhline(y=0, color='#e8c547', linestyle=':', alpha=0.3)
    
    ax1.set_ylabel('ARKK Price ($)', color='#3b82f6')
    ax2.set_ylabel('Net P/L ($)', color='#e8c547')
    ax1.tick_params(axis='y', labelcolor='#3b82f6')
    ax2.tick_params(axis='y', labelcolor='#e8c547')
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)
    
    ax1.set_title('ARKK PRICE vs STRATEGY NET P/L', fontsize=13, fontweight='bold', color='#e8c547')
    ax1.grid(True)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    plt.tight_layout()
    plt.savefig('output/bt_07_arkk_vs_pl.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("7/8 ARKK vs Net P/L")

    # ================================================================
    # CHART 8: Contract Count + Multiple Over Time
    # ================================================================
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), height_ratios=[1, 1])
    
    ax1.bar(dates, n_contracts, width=5, color='#8b5cf6', alpha=0.7)
    ax1.set_title('ACTIVE CONTRACTS', fontsize=11, fontweight='bold', color='#e8c547')
    ax1.set_ylabel('Contracts')
    ax1.grid(True, axis='y')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    
    # Multiple
    multiples = []
    for _, row in snaps.iterrows():
        if row['cost_basis'] > 0:
            multiples.append(row['position_value'] / row['cost_basis'])
        else:
            multiples.append(0)
    
    ax2.plot(dates, multiples, color='#e8c547', linewidth=2)
    ax2.axhline(y=2.0, color='#10b981', linestyle='--', alpha=0.4, linewidth=1)
    ax2.text(dates.iloc[0], 2.1, '2x PT Trigger', color='#10b981', fontsize=7)
    ax2.axhline(y=3.0, color='#ef4444', linestyle='--', alpha=0.4, linewidth=1)
    ax2.text(dates.iloc[0], 3.1, '3x PT Trigger', color='#ef4444', fontsize=7)
    ax2.axhline(y=0.7, color='#f59e0b', linestyle='--', alpha=0.4, linewidth=1)
    ax2.text(dates.iloc[0], 0.75, '30% Roll Trigger', color='#f59e0b', fontsize=7)
    ax2.set_title('POSITION MULTIPLE (PV / Cost Basis)', fontsize=11, fontweight='bold', color='#e8c547')
    ax2.set_ylabel('Multiple')
    ax2.set_ylim(0, min(max(multiples) * 1.1, 15))
    ax2.grid(True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    
    plt.tight_layout()
    plt.savefig('output/bt_08_contracts_multiple.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("8/8 Contracts & Multiple")

    print("\nAll 8 charts saved to output/")
    
    # Print summary stats
    print("\n" + "="*50)
    print("PERFORMANCE SUMMARY")
    print("="*50)
    final = snaps.iloc[-1]
    print("Starting Capital:  $100,000")
    print("Final Portfolio:   $" + str(int(final['position_value'] + final['reserve'])) + "")
    print("  Position Value:  $" + str(int(final['position_value'])))
    print("  Reserve:         $" + str(int(final['reserve'])))
    print("Net P/L:           $" + str(int(final['net_pl'])))
    print("Total Return:      " + str(round(final['net_pl'] / 100000 * 100, 1)) + "%")
    print("Cum Realized:      $" + str(int(final['cum_realized'])))
    print("Max Drawdown:      $" + str(int(net_pl.min())))
    
    n_rolls = len(txns[txns['action'] == 'ROLL_CLOSE'])
    n_pt = len(txns[txns['action'].str.startswith('PROFIT_TAKE')])
    n_trim = len(txns[txns['action'] == 'BETWEEN_TRIM'])
    n_reload = len(txns[txns['action'].str.startswith('RELOAD')])
    print("Rolls:             " + str(n_rolls))
    print("Profit Takes:      " + str(n_pt))
    print("Between Trims:     " + str(n_trim))
    print("Reloads:           " + str(n_reload))

if __name__ == '__main__':
    main()