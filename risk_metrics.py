"""
Strategy Risk/Reward Analytics
===============================
Computes comprehensive performance metrics and compares
against benchmark strategies (simple short, buy-and-hold puts).

Run: python risk_metrics.py
"""

import pandas as pd
import numpy as np
from datetime import datetime

def load_data():
    snaps = pd.read_csv('output/backtest_snapshots.csv')
    snaps['date'] = pd.to_datetime(snaps['date'])
    txns = pd.read_csv('output/backtest_transactions.csv')
    txns['date'] = pd.to_datetime(txns['date'])
    
    underlying = pd.read_csv('data/arkk_underlying.csv')
    underlying['date'] = pd.to_datetime(underlying['date'])
    
    return snaps, txns, underlying

def compute_metrics(snaps, txns, underlying):
    # Total portfolio = position_value + reserve
    snaps['total_portfolio'] = snaps['position_value'] + snaps['reserve']
    
    # Weekly returns on total portfolio
    snaps['weekly_return'] = snaps['total_portfolio'].pct_change()
    snaps['weekly_return_dollar'] = snaps['total_portfolio'].diff()
    
    # Net P/L series
    net_pl = snaps['net_pl']
    total_port = snaps['total_portfolio']
    
    start_date = snaps['date'].iloc[0]
    end_date = snaps['date'].iloc[-1]
    n_weeks = len(snaps) - 1
    years = (end_date - start_date).days / 365.25
    
    initial = 100000
    final = total_port.iloc[-1]
    
    print("=" * 70)
    print("STRATEGY PERFORMANCE METRICS")
    print("=" * 70)
    
    # ------------------------------------------------------------------
    # 1. RETURN METRICS
    # ------------------------------------------------------------------
    print("\n--- RETURN METRICS ---")
    total_return = (final - initial) / initial
    cagr = (final / initial) ** (1 / years) - 1 if years > 0 else 0
    
    print("Period:                " + start_date.strftime('%Y-%m-%d') + " to " + end_date.strftime('%Y-%m-%d'))
    print("Duration:              " + str(round(years, 2)) + " years (" + str(n_weeks) + " weekly observations)")
    print("Starting Capital:      $" + str(int(initial)))
    print("Final Portfolio:       $" + str(int(final)))
    print("Total Return:          " + str(round(total_return * 100, 2)) + "%")
    print("CAGR:                  " + str(round(cagr * 100, 2)) + "%")
    print("Cum. Realized P/L:     $" + str(int(snaps['cum_realized'].iloc[-1])))
    print("Unrealized P/L:        $" + str(int(snaps['position_value'].iloc[-1] - snaps['cost_basis'].iloc[-1])))
    
    # ------------------------------------------------------------------
    # 2. RISK METRICS
    # ------------------------------------------------------------------
    print("\n--- RISK METRICS ---")
    
    # Max drawdown on total portfolio
    rolling_max = total_port.cummax()
    drawdown = total_port - rolling_max
    max_dd = drawdown.min()
    max_dd_pct = (drawdown / rolling_max).min()
    
    # Drawdown duration
    in_dd = drawdown < 0
    dd_groups = (~in_dd).cumsum()
    dd_durations = in_dd.groupby(dd_groups).sum()
    max_dd_duration = dd_durations.max() if len(dd_durations) > 0 else 0
    
    # Net P/L max drawdown
    pl_peak = net_pl.cummax()
    pl_dd = net_pl - pl_peak
    max_pl_dd = pl_dd.min()
    
    # Weekly volatility
    weekly_returns = snaps['weekly_return'].dropna()
    vol_weekly = weekly_returns.std()
    vol_annual = vol_weekly * np.sqrt(52)
    
    # Downside deviation (for Sortino)
    negative_returns = weekly_returns[weekly_returns < 0]
    downside_dev = negative_returns.std() * np.sqrt(52) if len(negative_returns) > 0 else 0.01
    
    print("Max Drawdown ($):      $" + str(int(max_dd)))
    print("Max Drawdown (%):      " + str(round(max_dd_pct * 100, 2)) + "%")
    print("Max DD Duration:       " + str(int(max_dd_duration)) + " weeks")
    print("Net P/L Max DD:        $" + str(int(max_pl_dd)))
    print("Weekly Volatility:     " + str(round(vol_weekly * 100, 2)) + "%")
    print("Annualized Volatility: " + str(round(vol_annual * 100, 2)) + "%")
    print("Worst Week:            " + str(round(weekly_returns.min() * 100, 2)) + "%")
    print("Best Week:             " + str(round(weekly_returns.max() * 100, 2)) + "%")
    
    # ------------------------------------------------------------------
    # 3. RISK-ADJUSTED METRICS
    # ------------------------------------------------------------------
    print("\n--- RISK-ADJUSTED METRICS ---")
    
    rf_annual = 0.02  # risk-free rate
    rf_weekly = rf_annual / 52
    
    excess_returns = weekly_returns - rf_weekly
    sharpe = excess_returns.mean() / excess_returns.std() * np.sqrt(52) if excess_returns.std() > 0 else 0
    
    # Sortino (using downside deviation)
    sortino = (weekly_returns.mean() - rf_weekly) / (negative_returns.std()) * np.sqrt(52) if len(negative_returns) > 0 and negative_returns.std() > 0 else 0
    
    # Calmar (CAGR / max drawdown %)
    calmar = cagr / abs(max_dd_pct) if max_dd_pct != 0 else 0
    
    # Omega ratio (sum of gains / sum of losses above/below threshold)
    gains = weekly_returns[weekly_returns > rf_weekly] - rf_weekly
    losses = rf_weekly - weekly_returns[weekly_returns <= rf_weekly]
    omega = gains.sum() / losses.sum() if losses.sum() > 0 else float('inf')
    
    # Risk per dollar of profit
    if net_pl.iloc[-1] > 0:
        risk_per_profit = abs(max_dd) / net_pl.iloc[-1]
    else:
        risk_per_profit = float('inf')
    
    print("Sharpe Ratio:          " + str(round(sharpe, 3)))
    print("Sortino Ratio:         " + str(round(sortino, 3)))
    print("Calmar Ratio:          " + str(round(calmar, 3)))
    print("Omega Ratio:           " + str(round(omega, 3)))
    print("Risk per $ Profit:     $" + str(round(risk_per_profit, 2)))
    print("Return/Max DD:         " + str(round(total_return / abs(max_dd_pct), 2)) + "x")
    
    # ------------------------------------------------------------------
    # 4. TRADE ANALYSIS
    # ------------------------------------------------------------------
    print("\n--- TRADE ANALYSIS ---")
    
    realized_txns = txns[txns['realized_pnl'] != 0].copy()
    wins = realized_txns[realized_txns['realized_pnl'] > 0]
    losses = realized_txns[realized_txns['realized_pnl'] < 0]
    
    n_trades = len(realized_txns)
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n_trades if n_trades > 0 else 0
    
    avg_win = wins['realized_pnl'].mean() if n_wins > 0 else 0
    avg_loss = losses['realized_pnl'].mean() if n_losses > 0 else 0
    total_wins = wins['realized_pnl'].sum() if n_wins > 0 else 0
    total_losses = abs(losses['realized_pnl'].sum()) if n_losses > 0 else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
    
    # Expectancy
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    
    print("Total Transactions:    " + str(n_trades))
    print("Winners:               " + str(n_wins) + " (" + str(round(win_rate * 100, 1)) + "%)")
    print("Losers:                " + str(n_losses) + " (" + str(round((1 - win_rate) * 100, 1)) + "%)")
    print("Avg Win:               $" + str(int(avg_win)))
    print("Avg Loss:              $" + str(int(avg_loss)))
    print("Largest Win:           $" + str(int(wins['realized_pnl'].max())) if n_wins > 0 else "N/A")
    print("Largest Loss:          $" + str(int(losses['realized_pnl'].min())) if n_losses > 0 else "N/A")
    print("Profit Factor:         " + str(round(profit_factor, 3)))
    print("Expectancy per Trade:  $" + str(int(expectancy)))
    print("Total Realized Gains:  $" + str(int(total_wins)))
    print("Total Realized Losses: $" + str(int(total_losses)))
    
    # ------------------------------------------------------------------
    # 5. CAPITAL EFFICIENCY
    # ------------------------------------------------------------------
    print("\n--- CAPITAL EFFICIENCY ---")
    
    avg_deployed = snaps['cost_basis'].mean()
    avg_reserve = snaps['reserve'].mean()
    capital_utilization = avg_deployed / initial
    reserve_utilization = 1 - (avg_reserve / initial)
    
    # Max capital at risk
    max_at_risk = snaps['cost_basis'].max()
    return_on_risk = net_pl.iloc[-1] / max_at_risk if max_at_risk > 0 else 0
    
    print("Avg Capital Deployed:  $" + str(int(avg_deployed)))
    print("Avg Reserve:           $" + str(int(avg_reserve)))
    print("Capital Utilization:   " + str(round(capital_utilization * 100, 1)) + "%")
    print("Max Capital at Risk:   $" + str(int(max_at_risk)))
    print("Return on Max Risk:    " + str(round(return_on_risk * 100, 1)) + "%")
    
    # ------------------------------------------------------------------
    # 6. BENCHMARK COMPARISON: Simple Short ARKK
    # ------------------------------------------------------------------
    print("\n--- BENCHMARK: SIMPLE SHORT ARKK ---")
    
    # Match dates between underlying and our snapshots
    bench_dates = snaps['date'].tolist()
    arkk_start = snaps['arkk'].iloc[0]
    arkk_end = snaps['arkk'].iloc[-1]
    
    # Simple short: sell 100K worth at start, cover at end
    shares_short = int(initial / arkk_start)
    short_proceeds = shares_short * arkk_start
    cover_cost = shares_short * arkk_end
    short_pnl = short_proceeds - cover_cost
    short_return = short_pnl / initial
    
    # Build short equity curve for comparison
    short_equity = []
    for _, row in snaps.iterrows():
        price = row['arkk'] if pd.notna(row['arkk']) else arkk_start
        eq = initial + (arkk_start - price) * shares_short
        short_equity.append(eq)
    
    snaps['short_equity'] = short_equity
    short_returns = snaps['short_equity'].pct_change().dropna()
    short_vol = short_returns.std() * np.sqrt(52)
    short_sharpe = (short_returns.mean() - rf_weekly) / short_returns.std() * np.sqrt(52) if short_returns.std() > 0 else 0
    
    short_rolling_max = snaps['short_equity'].cummax()
    short_dd = (snaps['short_equity'] - short_rolling_max)
    short_max_dd_pct = (short_dd / short_rolling_max).min()
    
    print("Shares Shorted:        " + str(shares_short) + " @ $" + str(round(arkk_start, 2)))
    print("ARKK Start:            $" + str(round(arkk_start, 2)))
    print("ARKK End:              $" + str(round(arkk_end, 2)))
    print("Short P/L:             $" + str(int(short_pnl)))
    print("Short Return:          " + str(round(short_return * 100, 2)) + "%")
    print("Short Sharpe:          " + str(round(short_sharpe, 3)))
    print("Short Max DD (%):      " + str(round(short_max_dd_pct * 100, 2)) + "%")
    print("Short Ann. Vol:        " + str(round(short_vol * 100, 2)) + "%")
    
    # ------------------------------------------------------------------
    # 7. STRATEGY vs BENCHMARK COMPARISON
    # ------------------------------------------------------------------
    print("\n--- STRATEGY vs BENCHMARK ---")
    
    # Beta to short ARKK
    strat_rets = snaps['weekly_return'].dropna().values
    short_rets = short_returns.values
    min_len = min(len(strat_rets), len(short_rets))
    strat_rets = strat_rets[:min_len]
    short_rets = short_rets[:min_len]
    
    if len(strat_rets) > 1:
        covariance = np.cov(strat_rets, short_rets)[0][1]
        variance = np.var(short_rets)
        beta = covariance / variance if variance > 0 else 0
        correlation = np.corrcoef(strat_rets, short_rets)[0][1]
    else:
        beta = 0
        correlation = 0
    
    # Alpha (annualized)
    strat_ann_ret = (1 + np.mean(strat_rets)) ** 52 - 1
    bench_ann_ret = (1 + np.mean(short_rets)) ** 52 - 1
    alpha = strat_ann_ret - (rf_annual + beta * (bench_ann_ret - rf_annual))
    
    print("                       Strategy    Short ARKK")
    print("Total Return:          " + str(round(total_return * 100, 1)).rjust(8) + "%     " + str(round(short_return * 100, 1)).rjust(8) + "%")
    print("Sharpe:                " + str(round(sharpe, 3)).rjust(8) + "      " + str(round(short_sharpe, 3)).rjust(8))
    print("Max DD (%):            " + str(round(max_dd_pct * 100, 1)).rjust(8) + "%     " + str(round(short_max_dd_pct * 100, 1)).rjust(8) + "%")
    print("Ann. Volatility:       " + str(round(vol_annual * 100, 1)).rjust(8) + "%     " + str(round(short_vol * 100, 1)).rjust(8) + "%")
    print("")
    print("Beta to Short ARKK:    " + str(round(beta, 3)))
    print("Correlation:           " + str(round(correlation, 3)))
    print("Alpha (annualized):    " + str(round(alpha * 100, 2)) + "%")
    
    # ------------------------------------------------------------------
    # 8. ROLLING METRICS
    # ------------------------------------------------------------------
    print("\n--- ROLLING METRICS (13-week / ~3 months) ---")
    
    if len(weekly_returns) >= 13:
        rolling_sharpe = weekly_returns.rolling(13).apply(
            lambda x: (x.mean() - rf_weekly) / x.std() * np.sqrt(52) if x.std() > 0 else 0
        )
        
        print("Best 13-wk Sharpe:     " + str(round(rolling_sharpe.max(), 3)))
        print("Worst 13-wk Sharpe:    " + str(round(rolling_sharpe.min(), 3)))
        print("Median 13-wk Sharpe:   " + str(round(rolling_sharpe.median(), 3)))
        
        pct_positive = (rolling_sharpe > 0).sum() / rolling_sharpe.count() * 100
        print("% Periods Sharpe > 0:  " + str(round(pct_positive, 1)) + "%")
    
    print("\n" + "=" * 70)


if __name__ == '__main__':
    snaps, txns, underlying = load_data()
    compute_metrics(snaps, txns, underlying)