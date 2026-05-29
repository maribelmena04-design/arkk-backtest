"""
Option Recovery Analysis
=========================
Answers: "When a put position declines X% from purchase price,
what is the probability it recovers within N weeks?"

This is a STRUCTURAL analysis of option pricing behavior,
not a backtest optimization. The results generalize across underlyings.

Run: python recovery_analysis.py
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from data_loader import OptionsData

def analyze_recovery(data, strikes_to_track=None):
    """
    For each date/strike combination, track forward price paths
    and compute recovery statistics at different drawdown levels.
    """
    dates = data.get_dates()
    
    if strikes_to_track is None:
        # Track strikes at ~20-25% OTM and ~35-40% OTM for each date
        strikes_to_track = []
        for d in dates:
            price = data.get_underlying_price(d)
            if not price:
                continue
            for otm in [0.20, 0.25, 0.30, 0.35, 0.40]:
                candidates = data.get_strikes_near(d, price, otm, n=1)
                if candidates:
                    strikes_to_track.append({
                        'entry_date': d,
                        'strike': candidates[0]['strike'],
                        'entry_price': candidates[0]['mid'],
                        'otm_pct': otm,
                        'arkk_at_entry': price
                    })
    
    # For each entry, track what happens over subsequent weeks
    results = []
    
    for entry in strikes_to_track:
        entry_date = entry['entry_date']
        strike = entry['strike']
        entry_px = entry['entry_price']
        
        if entry_px is None or entry_px <= 0:
            continue
        
        entry_idx = dates.index(entry_date) if entry_date in dates else -1
        if entry_idx < 0:
            continue
        
        # Track forward from entry
        max_drawdown_seen = 0
        recovered_from = {}  # {drawdown_level: True/False}
        drawdown_levels = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
        hit_drawdown = {level: False for level in drawdown_levels}
        recovered_after = {level: False for level in drawdown_levels}
        weeks_to_recover = {level: None for level in drawdown_levels}
        min_price_after_dd = {level: None for level in drawdown_levels}
        max_price_after_dd = {level: None for level in drawdown_levels}
        
        for fwd_idx in range(entry_idx + 1, min(entry_idx + 52, len(dates))):
            fwd_date = dates[fwd_idx]
            weeks_out = fwd_idx - entry_idx
            
            # Try to find this strike in forward date
            opt = data.get_option(fwd_date, strike)
            if opt is None or opt['mid'] is None:
                continue
            
            fwd_px = opt['mid']
            change_pct = (fwd_px - entry_px) / entry_px
            drawdown = max(0, -change_pct)
            
            if drawdown > max_drawdown_seen:
                max_drawdown_seen = drawdown
            
            # Check each drawdown level
            for level in drawdown_levels:
                if drawdown >= level:
                    hit_drawdown[level] = True
                
                if hit_drawdown[level] and not recovered_after[level]:
                    # Track min/max after hitting this drawdown
                    if min_price_after_dd[level] is None or fwd_px < min_price_after_dd[level]:
                        min_price_after_dd[level] = fwd_px
                    if max_price_after_dd[level] is None or fwd_px > max_price_after_dd[level]:
                        max_price_after_dd[level] = fwd_px
                    
                    if fwd_px >= entry_px:
                        recovered_after[level] = True
                        weeks_to_recover[level] = weeks_out
        
        for level in drawdown_levels:
            if hit_drawdown[level]:
                # Compute best recovery ratio after hitting this drawdown
                best_ratio = None
                if max_price_after_dd[level] is not None:
                    best_ratio = max_price_after_dd[level] / entry_px
                
                results.append({
                    'entry_date': entry_date,
                    'strike': strike,
                    'entry_price': entry_px,
                    'otm_pct': entry.get('otm_pct', 0),
                    'arkk_at_entry': entry.get('arkk_at_entry', 0),
                    'drawdown_level': level,
                    'recovered': recovered_after[level],
                    'weeks_to_recover': weeks_to_recover[level],
                    'max_drawdown': max_drawdown_seen,
                    'best_recovery_ratio': best_ratio,
                })
    
    return pd.DataFrame(results)


def print_recovery_table(df):
    """Print recovery probability at each drawdown level."""
    print("\n" + "=" * 70)
    print("OPTION RECOVERY PROBABILITY ANALYSIS")
    print("=" * 70)
    print("\nQuestion: When a put declines X% from purchase price,")
    print("how often does it recover to breakeven within 52 weeks?\n")
    
    print("Drawdown    Occurrences    Recovery%    Avg Weeks    Best Recovery")
    print("-" * 70)
    
    for level in sorted(df['drawdown_level'].unique()):
        subset = df[df['drawdown_level'] == level]
        n = len(subset)
        n_recovered = subset['recovered'].sum()
        pct = n_recovered / n * 100 if n > 0 else 0
        
        avg_weeks = subset[subset['recovered']]['weeks_to_recover'].mean()
        avg_weeks_str = str(round(avg_weeks, 1)) if not np.isnan(avg_weeks) else "N/A"
        
        avg_best = subset['best_recovery_ratio'].mean()
        avg_best_str = str(round(avg_best, 2)) + "x" if not np.isnan(avg_best) else "N/A"
        
        print(str(int(level * 100)).rjust(5) + "%       " +
              str(n).rjust(5) + "         " +
              str(round(pct, 1)).rjust(5) + "%       " +
              avg_weeks_str.rjust(5) + "         " +
              avg_best_str.rjust(6))
    
    # Break down by OTM percentage
    print("\n\nRECOVERY BY OTM PERCENTAGE:")
    print("-" * 70)
    
    for otm in sorted(df['otm_pct'].unique()):
        subset = df[df['otm_pct'] == otm]
        print("\n  " + str(int(otm * 100)) + "% OTM puts:")
        
        for level in [0.20, 0.25, 0.30, 0.35, 0.40]:
            dd_subset = subset[subset['drawdown_level'] == level]
            if len(dd_subset) == 0:
                continue
            n = len(dd_subset)
            pct = dd_subset['recovered'].sum() / n * 100
            best = dd_subset['best_recovery_ratio'].mean()
            print("    " + str(int(level * 100)) + "% DD: " +
                  str(round(pct, 0)).rjust(4) + "% recover (" + str(n) + " cases)" +
                  "  best avg " + str(round(best, 2)) + "x")
    
    # Key insight: at what drawdown does recovery become unlikely?
    print("\n\nKEY INSIGHT — RECOVERY CLIFF:")
    print("-" * 70)
    
    prev_pct = 100
    for level in sorted(df['drawdown_level'].unique()):
        subset = df[df['drawdown_level'] == level]
        n = len(subset)
        pct = subset['recovered'].sum() / n * 100 if n > 0 else 0
        drop = prev_pct - pct
        
        marker = ""
        if drop > 10:
            marker = "  <<< SIGNIFICANT DROP"
        if pct < 30:
            marker = "  <<< BELOW 30% — ROLL JUSTIFIED"
        
        print("  " + str(int(level * 100)) + "% drawdown: " +
              str(round(pct, 1)).rjust(5) + "% recovery rate" +
              " (delta: " + str(round(-drop, 1)) + "pp)" + marker)
        prev_pct = pct


def plot_recovery(df):
    """Generate recovery probability visualization."""
    plt.rcParams.update({
        'figure.facecolor': '#0a0a0a', 'axes.facecolor': '#0f0f0f',
        'axes.edgecolor': '#333', 'axes.labelcolor': '#ccc',
        'text.color': '#ccc', 'xtick.color': '#888', 'ytick.color': '#888',
        'grid.color': '#1a1a1a', 'grid.linestyle': '--', 'grid.alpha': 0.5,
        'font.family': 'monospace', 'font.size': 9,
    })
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    
    # Left: Recovery probability curve
    levels = sorted(df['drawdown_level'].unique())
    probs = []
    for level in levels:
        subset = df[df['drawdown_level'] == level]
        probs.append(subset['recovered'].mean() * 100)
    
    ax1.plot(levels, probs, color='#e8c547', linewidth=2.5, marker='o', markersize=8)
    ax1.fill_between(levels, probs, alpha=0.1, color='#e8c547')
    ax1.axhline(y=30, color='#ef4444', linestyle='--', alpha=0.5)
    ax1.text(0.45, 32, '30% recovery = roll justified', color='#ef4444', fontsize=8)
    ax1.axhline(y=50, color='#f59e0b', linestyle='--', alpha=0.3)
    ax1.text(0.45, 52, '50% coin flip', color='#f59e0b', fontsize=8)
    
    ax1.set_xlabel('Drawdown from Entry (%)')
    ax1.set_ylabel('Recovery Probability (%)')
    ax1.set_title('PUT RECOVERY PROBABILITY vs DRAWDOWN', fontsize=11, fontweight='bold', color='#e8c547')
    ax1.set_xticks(levels)
    ax1.set_xticklabels([str(int(l * 100)) + '%' for l in levels])
    ax1.grid(True)
    
    # Right: Recovery by OTM percentage
    otm_levels = sorted(df['otm_pct'].unique())
    colors = ['#3b82f6', '#10b981', '#e8c547', '#f59e0b', '#ef4444']
    
    for i, otm in enumerate(otm_levels):
        subset = df[df['otm_pct'] == otm]
        otm_probs = []
        for level in levels:
            dd_sub = subset[subset['drawdown_level'] == level]
            if len(dd_sub) > 0:
                otm_probs.append(dd_sub['recovered'].mean() * 100)
            else:
                otm_probs.append(np.nan)
        
        color = colors[i % len(colors)]
        ax2.plot(levels, otm_probs, color=color, linewidth=1.5, marker='s', markersize=5,
                label=str(int(otm * 100)) + '% OTM', alpha=0.8)
    
    ax2.set_xlabel('Drawdown from Entry (%)')
    ax2.set_ylabel('Recovery Probability (%)')
    ax2.set_title('RECOVERY BY OTM PERCENTAGE', fontsize=11, fontweight='bold', color='#e8c547')
    ax2.set_xticks(levels)
    ax2.set_xticklabels([str(int(l * 100)) + '%' for l in levels])
    ax2.legend(fontsize=8)
    ax2.grid(True)
    
    plt.tight_layout()
    plt.savefig('output/recovery_analysis.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("\nChart saved to output/recovery_analysis.png")


if __name__ == '__main__':
    data = OptionsData()
    print("Running recovery analysis across all dates and strikes...")
    print("This may take a minute...\n")
    
    df = analyze_recovery(data)
    
    if len(df) > 0:
        print_recovery_table(df)
        plot_recovery(df)
        df.to_csv('output/recovery_analysis.csv', index=False)
        print("\nRaw data saved to output/recovery_analysis.csv")
        print("Total observations: " + str(len(df)))
    else:
        print("No recovery data generated. Check data files.")