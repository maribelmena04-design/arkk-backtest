"""
ARKK Put Strategy — Data Visualization
========================================
Generates charts from collected options chain data.
Run from the arkk_backtest directory:
    python visualize.py
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from datetime import datetime
from data_loader import OptionsData
import os

# Dark theme
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

def parse_date(d):
    return datetime.strptime(d, '%Y-%m-%d')

def main():
    os.makedirs('output', exist_ok=True)
    data = OptionsData()
    dates = data.get_dates()
    
    # Collect time series
    ts_dates = []
    ts_arkk = []
    ts_80p_mid = []
    ts_65p_mid = []
    ts_80p_iv = []
    ts_65p_iv = []
    ts_80p_delta = []
    ts_65p_delta = []
    ts_pos_value = []
    
    entry_positions = [
        {'strike': 80, 'contracts': 8},
        {'strike': 65, 'contracts': 22}
    ]
    
    for d in dates:
        dt = parse_date(d)
        price = data.get_underlying_price(d)
        opt_80 = data.get_option(d, 80)
        opt_65 = data.get_option(d, 65)
        pv = data.get_position_value(d, entry_positions)
        
        ts_dates.append(dt)
        ts_arkk.append(price if price else np.nan)
        
        if opt_80:
            ts_80p_mid.append(opt_80['mid'])
            ts_80p_iv.append(opt_80['iv'] if opt_80['iv'] else np.nan)
            ts_80p_delta.append(opt_80['delta'] if opt_80['delta'] else np.nan)
        else:
            ts_80p_mid.append(np.nan)
            ts_80p_iv.append(np.nan)
            ts_80p_delta.append(np.nan)
        
        if opt_65:
            ts_65p_mid.append(opt_65['mid'])
            ts_65p_iv.append(opt_65['iv'] if opt_65['iv'] else np.nan)
            ts_65p_delta.append(opt_65['delta'] if opt_65['delta'] else np.nan)
        else:
            ts_65p_mid.append(np.nan)
            ts_65p_iv.append(np.nan)
            ts_65p_delta.append(np.nan)
        
        ts_pos_value.append(pv['total_value'])
    
    # Also track the rolled strikes ($95p, $78p after Roll 1 on ~Dec 15)
    ts_95p_mid = []
    ts_78p_mid = []
    ts_110p_mid = []
    ts_115p_mid = []
    
    for d in dates:
        opt_95 = data.get_option(d, 95)
        opt_78 = data.get_option(d, 78)
        opt_110 = data.get_option(d, 110)
        opt_115 = data.get_option(d, 115)
        ts_95p_mid.append(opt_95['mid'] if opt_95 else np.nan)
        ts_78p_mid.append(opt_78['mid'] if opt_78 else np.nan)
        ts_110p_mid.append(opt_110['mid'] if opt_110 else np.nan)
        ts_115p_mid.append(opt_115['mid'] if opt_115 else np.nan)
    
    # ================================================================
    # CHART 1: ARKK Price + Key Strategy Events
    # ================================================================
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(ts_dates, ts_arkk, color='#3b82f6', linewidth=2, label='ARKK Close')
    ax.fill_between(ts_dates, ts_arkk, alpha=0.1, color='#3b82f6')
    
    # Mark key events
    events = {
        '2020-10-15': ('Entry', '#3b82f6', 'v'),
        '2020-12-15': ('Roll 1', '#f59e0b', 's'),
        '2021-01-21': ('Roll 2', '#f59e0b', 's'),
        '2021-02-14': ('Roll 3', '#f59e0b', 's'),
        '2021-03-04': ('Profit Take 1', '#10b981', '^'),
        '2021-04-15': ('Reload 1', '#8b5cf6', 'D'),
        '2021-05-13': ('Profit Take 2', '#10b981', '^'),
        '2021-06-10': ('Reload 2', '#8b5cf6', 'D'),
    }
    
    for evt_date, (label, color, marker) in events.items():
        dt = parse_date(evt_date)
        if dt in ts_dates:
            idx = ts_dates.index(dt)
            price_val = ts_arkk[idx]
        else:
            # Find nearest date
            nearest = min(ts_dates, key=lambda x: abs((x - dt).days))
            idx = ts_dates.index(nearest)
            price_val = ts_arkk[idx]
        
        if not np.isnan(price_val):
            ax.scatter([dt], [price_val], color=color, s=80, marker=marker, zorder=5, edgecolors='white', linewidths=0.5)
            ax.annotate(label, (dt, price_val), textcoords="offset points", 
                       xytext=(0, 15), ha='center', fontsize=7, color=color, fontweight='bold')
    
    ax.axhline(y=159.7, color='#ef4444', linestyle='--', alpha=0.3, linewidth=1)
    ax.text(ts_dates[-1], 161, 'Peak $159.70', color='#ef4444', fontsize=7, ha='right')
    
    ax.set_title('ARKK PRICE ACTION & STRATEGY EVENTS', fontsize=12, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Price ($)')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.tight_layout()
    plt.savefig('output/01_arkk_price_events.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 1: ARKK Price & Events")
    
    # ================================================================
    # CHART 2: Entry Positions — $80p and $65p Mid Price Over Time
    # ================================================================
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[1, 1])
    
    ax1.plot(ts_dates, ts_80p_mid, color='#e8c547', linewidth=2, label='$80 Put Mid')
    ax1.axhline(y=10.15, color='#e8c547', linestyle=':', alpha=0.4, linewidth=1)
    ax1.text(ts_dates[0], 10.5, 'Entry: $10.15', color='#e8c547', fontsize=7)
    ax1.set_title('ENTRY POSITION: $80 PUT (8 contracts)', fontsize=10, fontweight='bold', color='#e8c547')
    ax1.set_ylabel('Mid Price ($)')
    ax1.grid(True)
    ax1.legend(fontsize=8)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    
    ax2.plot(ts_dates, ts_65p_mid, color='#8b5cf6', linewidth=2, label='$65 Put Mid')
    ax2.axhline(y=5.40, color='#8b5cf6', linestyle=':', alpha=0.4, linewidth=1)
    ax2.text(ts_dates[0], 5.7, 'Entry: $5.40', color='#8b5cf6', fontsize=7)
    ax2.set_title('ENTRY POSITION: $65 PUT (22 contracts)', fontsize=10, fontweight='bold', color='#8b5cf6')
    ax2.set_ylabel('Mid Price ($)')
    ax2.grid(True)
    ax2.legend(fontsize=8)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    
    plt.tight_layout()
    plt.savefig('output/02_entry_positions.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 2: Entry Position Tracking")
    
    # ================================================================
    # CHART 3: Position Value Over Time (Buy & Hold the entry)
    # ================================================================
    fig, ax = plt.subplots(figsize=(14, 6))
    
    colors = ['#10b981' if v >= 20000 else '#ef4444' for v in ts_pos_value]
    ax.plot(ts_dates, ts_pos_value, color='#e8c547', linewidth=2)
    ax.fill_between(ts_dates, ts_pos_value, 20000, 
                    where=[v >= 20000 for v in ts_pos_value], 
                    alpha=0.15, color='#10b981', interpolate=True)
    ax.fill_between(ts_dates, ts_pos_value, 20000, 
                    where=[v < 20000 for v in ts_pos_value], 
                    alpha=0.15, color='#ef4444', interpolate=True)
    ax.axhline(y=20000, color='#ffffff', linestyle='--', alpha=0.2, linewidth=1)
    ax.text(ts_dates[-1], 20500, 'Entry Value: $20,000', color='#666', fontsize=7, ha='right')
    
    # 30% roll trigger line
    ax.axhline(y=14000, color='#ef4444', linestyle=':', alpha=0.3, linewidth=1)
    ax.text(ts_dates[-1], 14300, '30% Roll Trigger: $14,000', color='#ef4444', fontsize=7, ha='right')
    
    ax.set_title('ENTRY PORTFOLIO VALUE (Buy & Hold — No Rolls)', fontsize=12, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Portfolio Value ($)')
    ax.grid(True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.tight_layout()
    plt.savefig('output/03_position_value.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 3: Position Value")
    
    # ================================================================
    # CHART 4: IV Evolution for Key Strikes
    # ================================================================
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.plot(ts_dates, [iv * 100 if iv and not np.isnan(iv) else np.nan for iv in ts_80p_iv], 
            color='#e8c547', linewidth=2, label='$80 Put IV', marker='o', markersize=3)
    ax.plot(ts_dates, [iv * 100 if iv and not np.isnan(iv) else np.nan for iv in ts_65p_iv], 
            color='#8b5cf6', linewidth=2, label='$65 Put IV', marker='o', markersize=3)
    
    ax.set_title('IMPLIED VOLATILITY EVOLUTION', fontsize=12, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Implied Volatility (%)')
    ax.grid(True)
    ax.legend(fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.tight_layout()
    plt.savefig('output/04_iv_evolution.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 4: IV Evolution")
    
    # ================================================================
    # CHART 5: Key Strike Prices — All Traded Strikes Over Time
    # ================================================================
    fig, ax = plt.subplots(figsize=(14, 6))
    
    ax.plot(ts_dates, ts_65p_mid, color='#8b5cf6', linewidth=1.5, label='$65p (deep OTM entry)', alpha=0.8)
    ax.plot(ts_dates, ts_80p_mid, color='#e8c547', linewidth=1.5, label='$80p (moderate entry)', alpha=0.8)
    ax.plot(ts_dates, ts_95p_mid, color='#3b82f6', linewidth=1.5, label='$95p (Roll 1 strike)', alpha=0.8)
    ax.plot(ts_dates, ts_110p_mid, color='#10b981', linewidth=1.5, label='$110p (Roll 3 / PT strike)', alpha=0.8)
    ax.plot(ts_dates, ts_115p_mid, color='#ef4444', linewidth=1.5, label='$115p (Roll 2 strike)', alpha=0.8)
    
    ax.set_title('PUT MID PRICES — KEY STRIKES OVER TIME', fontsize=12, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Mid Price ($)')
    ax.grid(True)
    ax.legend(fontsize=8, loc='upper right')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.tight_layout()
    plt.savefig('output/05_key_strikes.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 5: Key Strike Prices")
    
    # ================================================================
    # CHART 6: ARKK Price vs Position Value (Dual Axis)
    # ================================================================
    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()
    
    ax1.plot(ts_dates, ts_arkk, color='#3b82f6', linewidth=2, label='ARKK Price')
    ax2.plot(ts_dates, ts_pos_value, color='#e8c547', linewidth=2, label='Position Value', linestyle='--')
    
    ax1.set_ylabel('ARKK Price ($)', color='#3b82f6')
    ax2.set_ylabel('Position Value ($)', color='#e8c547')
    ax1.tick_params(axis='y', labelcolor='#3b82f6')
    ax2.tick_params(axis='y', labelcolor='#e8c547')
    
    ax1.set_title('ARKK PRICE vs ENTRY POSITION VALUE (Inverse Correlation)', fontsize=12, fontweight='bold', color='#e8c547')
    ax1.grid(True)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=8)
    
    plt.tight_layout()
    plt.savefig('output/06_price_vs_position.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 6: Price vs Position Value")
    
    # ================================================================
    # CHART 7: Delta Exposure Over Time
    # ================================================================
    fig, ax = plt.subplots(figsize=(14, 5))
    
    total_deltas = []
    for i in range(len(ts_dates)):
        d80 = ts_80p_delta[i] if not np.isnan(ts_80p_delta[i]) else 0
        d65 = ts_65p_delta[i] if not np.isnan(ts_65p_delta[i]) else 0
        total_delta = (d80 * 8 * 100) + (d65 * 22 * 100)
        total_deltas.append(total_delta)
    
    ax.bar(ts_dates, total_deltas, width=4, color='#ef4444', alpha=0.7)
    ax.set_title('PORTFOLIO DELTA EXPOSURE (Entry Positions)', fontsize=12, fontweight='bold', color='#e8c547')
    ax.set_ylabel('Total Delta (share equivalents)')
    ax.grid(True, axis='y')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.tight_layout()
    plt.savefig('output/07_delta_exposure.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✅ Chart 7: Delta Exposure")
    
    # ================================================================
    # CHART 8: IV Surface Snapshot (Latest Date)
    # ================================================================
    latest = dates[-1]
    chain = data.get_chain(latest)
    if chain is not None:
        fig, ax = plt.subplots(figsize=(14, 6))
        
        strikes = chain['strike'].values
        ivs = chain['iv'].values * 100
        deltas = chain['delta'].values
        
        sc = ax.scatter(strikes, ivs, c=[abs(d) for d in deltas], cmap='RdYlGn_r', 
                       s=60, edgecolors='#333', linewidths=0.5, zorder=5)
        ax.plot(strikes, ivs, color='#e8c547', linewidth=1, alpha=0.5)
        
        plt.colorbar(sc, label='|Delta|', ax=ax)
        
        price = data.get_underlying_price(latest)
        if price:
            ax.axvline(x=price, color='#3b82f6', linestyle='--', alpha=0.5, linewidth=1)
            ax.text(price + 1, max(ivs) - 2, f'ARKK ${price:.0f}', color='#3b82f6', fontsize=8)
        
        ax.set_title(f'IV SMILE — {latest} (Color = |Delta|)', fontsize=12, fontweight='bold', color='#e8c547')
        ax.set_xlabel('Strike ($)')
        ax.set_ylabel('Implied Volatility (%)')
        ax.grid(True)
        plt.tight_layout()
        plt.savefig('output/08_iv_surface.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("✅ Chart 8: IV Surface")
    
    print(f"\n🎯 All charts saved to output/ directory")
    print(f"   Open them in VSCode or any image viewer")

if __name__ == '__main__':
    main()