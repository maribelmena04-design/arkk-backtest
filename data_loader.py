"""
Data Loader for ARKK Options Backtest
======================================
Reads all CSV files from the data/ directory and provides
lookup functions for the strategy engine.
"""

import os
import pandas as pd
from datetime import datetime

class OptionsData:
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.chains = {}       # {date_str: DataFrame}
        self.dates = []        # sorted list of available dates
        self.underlying = None # DataFrame of underlying prices
        self._load_all()
    
    def _load_all(self):
        """Load all option chain CSVs and underlying prices."""
        # Load option chains
        for filename in sorted(os.listdir(self.data_dir)):
            if filename.startswith('arkk_options_') and filename.endswith('.csv'):
                date_str = filename.replace('arkk_options_', '').replace('.csv', '')
                filepath = os.path.join(self.data_dir, filename)
                try:
                    df = pd.read_csv(filepath)
                    self.chains[date_str] = df
                    self.dates.append(date_str)
                except Exception as e:
                    print(f"Warning: Could not load {filename}: {e}")
        
        # Load underlying prices
        underlying_path = os.path.join(self.data_dir, 'arkk_underlying.csv')
        if os.path.exists(underlying_path):
            self.underlying = pd.read_csv(underlying_path)
        
        print(f"Loaded {len(self.chains)} option chain snapshots")
        print(f"Date range: {self.dates[0]} to {self.dates[-1]}")
    
    def get_dates(self):
        """Return sorted list of available dates."""
        return self.dates
    
    def get_chain(self, date_str):
        """Get full option chain for a specific date."""
        if date_str in self.chains:
            return self.chains[date_str]
        return None
    
    def get_option(self, date_str, strike, expiration=None):
        """
        Look up a specific option by date and strike.
        Returns dict with bid, ask, mid, iv, delta, gamma, theta, vega.
        If strike not found exactly, finds nearest available strike.
        """
        chain = self.get_chain(date_str)
        if chain is None:
            return None
        
        # Filter by expiration if specified
        if expiration is not None:
            chain = chain[chain['expiration'] == expiration]
        
        # Try exact strike match first
        row = chain[chain['strike'] == strike]
        
        # If no exact match, find nearest strike
        if row.empty:
            nearest_idx = (chain['strike'] - strike).abs().idxmin()
            row = chain.loc[[nearest_idx]]
            actual_strike = chain.loc[nearest_idx, 'strike']
            if abs(actual_strike - strike) > 3:
                # Strike is too far off — likely adjusted strikes
                # Try matching within $2.50 range (covers distribution adjustments)
                close = chain[(chain['strike'] >= strike - 2.5) & (chain['strike'] <= strike + 2.5)]
                if not close.empty:
                    row = close.iloc[[0]]
                else:
                    return None
        
        row = row.iloc[0]
        return {
            'date': date_str,
            'strike': row['strike'],
            'bid': row['bid'],
            'ask': row['ask'],
            'mid': row['mid'],
            'iv': row['iv'],
            'delta': row['delta'],
            'gamma': row['gamma'],
            'theta': row['theta'],
            'vega': row['vega']
        }
    
    def get_underlying_price(self, date_str):
        """Get ARKK closing price for a date."""
        if self.underlying is None:
            return None
        row = self.underlying[self.underlying['date'] == date_str]
        if row.empty:
            return None
        return row.iloc[0]['close']
    
    def get_strikes_near(self, date_str, target_price, otm_pct, n=3):
        """
        Find put strikes near a target OTM percentage.
        For puts, OTM means strike < current price.
        
        Args:
            date_str: observation date
            target_price: current underlying price
            otm_pct: how far OTM (e.g., 0.22 for 22% OTM)
            n: number of nearby strikes to return
        
        Returns:
            List of dicts with option data for strikes near the target
        """
        chain = self.get_chain(date_str)
        if chain is None:
            return []
        
        target_strike = target_price * (1 - otm_pct)
        
        # Sort by distance from target
        chain = chain.copy()
        chain['distance'] = (chain['strike'] - target_strike).abs()
        nearest = chain.nsmallest(n, 'distance')
        
        results = []
        for _, row in nearest.iterrows():
            results.append({
                'strike': row['strike'],
                'bid': row['bid'],
                'ask': row['ask'],
                'mid': row['mid'],
                'iv': row['iv'],
                'delta': row['delta'],
                'gamma': row['gamma'],
                'theta': row['theta'],
                'vega': row['vega'],
                'otm_pct': round(1 - row['strike'] / target_price, 4)
            })
        
        return results
    
    def get_position_value(self, date_str, positions):
        """
        Calculate total market value of a list of positions.
        
        Args:
            date_str: observation date
            positions: list of dicts with {'strike': float, 'contracts': int, 'expiration': str}
        
        Returns:
            dict with total value, per-position breakdown, and Greeks
        """
        total_value = 0
        total_delta = 0
        total_theta = 0
        total_vega = 0
        breakdown = []
        
        for pos in positions:
            opt = self.get_option(date_str, pos['strike'], pos.get('expiration'))
            if opt is None:
                breakdown.append({
                    'strike': pos['strike'],
                    'contracts': pos['contracts'],
                    'status': 'NOT_FOUND'
                })
                continue
            
            qty = pos['contracts']
            value = opt['mid'] * qty * 100  # each contract = 100 shares
            
            breakdown.append({
                'strike': opt['strike'],
                'contracts': qty,
                'bid': opt['bid'],
                'ask': opt['ask'],
                'mid': opt['mid'],
                'iv': opt['iv'],
                'delta': opt['delta'],
                'value': value,
                'status': 'OK'
            })
            
            total_value += value
            if opt['delta'] is not None:
                total_delta += opt['delta'] * qty * 100
            if opt['theta'] is not None:
                total_theta += opt['theta'] * qty * 100
            if opt['vega'] is not None:
                total_vega += opt['vega'] * qty * 100
        
        return {
            'date': date_str,
            'total_value': round(total_value, 2),
            'total_delta': round(total_delta, 2),
            'total_theta': round(total_theta, 2),
            'total_vega': round(total_vega, 2),
            'positions': breakdown
        }
    
    def summary(self):
        """Print summary of loaded data."""
        print(f"\n{'='*60}")
        print(f"ARKK OPTIONS DATA SUMMARY")
        print(f"{'='*60}")
        print(f"Snapshots loaded: {len(self.chains)}")
        print(f"Date range: {self.dates[0]} to {self.dates[-1]}")
        print(f"\nAvailable dates:")
        for d in self.dates:
            chain = self.chains[d]
            n_strikes = len(chain)
            strike_min = chain['strike'].min()
            strike_max = chain['strike'].max()
            price = self.get_underlying_price(d)
            price_str = f"  ARKK: ${price}" if price else ""
            print(f"  {d}  |  {n_strikes} strikes  |  ${strike_min} - ${strike_max}{price_str}")


if __name__ == '__main__':
    # Test the data loader
    data = OptionsData()
    data.summary()
    
    print(f"\n{'='*60}")
    print("TEST: Look up our entry positions (Oct 15, 2020)")
    print(f"{'='*60}")
    
    # Look up our original entry strikes
    opt_80 = data.get_option('2020-10-15', 80)
    opt_65 = data.get_option('2020-10-15', 65)
    
    if opt_80:
        print(f"\n$80 Put: bid=${opt_80['bid']}, ask=${opt_80['ask']}, mid=${opt_80['mid']}, "
              f"IV={opt_80['iv']}, delta={opt_80['delta']}")
    
    if opt_65:
        print(f"$65 Put: bid=${opt_65['bid']}, ask=${opt_65['ask']}, mid=${opt_65['mid']}, "
              f"IV={opt_65['iv']}, delta={opt_65['delta']}")
    
    print(f"\n{'='*60}")
    print("TEST: Track $80 put across all dates")
    print(f"{'='*60}")
    
    for date_str in data.get_dates():
        opt = data.get_option(date_str, 80)
        price = data.get_underlying_price(date_str)
        if opt:
            print(f"  {date_str}  |  ARKK: ${price or 'N/A':>6}  |  $80p mid: ${opt['mid']:>6}  |  "
                  f"IV: {opt['iv'] or 'N/A'}  |  delta: {opt['delta']}")
    
    print(f"\n{'='*60}")
    print("TEST: Position value for our entry portfolio")
    print(f"{'='*60}")
    
    positions = [
        {'strike': 80, 'contracts': 8},
        {'strike': 65, 'contracts': 22}
    ]
    
    for date_str in data.get_dates()[:5]:  # first 5 dates
        pv = data.get_position_value(date_str, positions)
        print(f"  {date_str}  |  Position: ${pv['total_value']:>10,.2f}  |  "
              f"Delta: {pv['total_delta']:>8,.0f}  |  Theta: ${pv['total_theta']:>6,.0f}/day")