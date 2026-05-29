"""
Data Loader for ARKK Options Backtest
======================================
Reads all CSV files from the data/ directory (including monthly subdirectories)
and provides lookup functions for the strategy engine.
"""

import os
import pandas as pd
import numpy as np

class OptionsData:
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.chains = {}
        self.dates = []
        self.underlying = None
        self._load_all()
    
    def _load_all(self):
        for root, dirs, files in os.walk(self.data_dir):
            for filename in sorted(files):
                if filename.startswith('arkk_options_') and filename.endswith('.csv'):
                    date_str = filename.replace('arkk_options_', '').replace('.csv', '')
                    filepath = os.path.join(root, filename)
                    try:
                        df = pd.read_csv(filepath)
                        df.columns = df.columns.str.lower().str.strip()
                        df.columns = df.columns.str.replace('/', '_')
                        if 'strike' in df.columns and 'bid' in df.columns:
                            # Force numeric types on key columns
                            for col in ['strike', 'bid', 'ask', 'mid', 'iv', 'delta', 'gamma', 'theta', 'vega']:
                                if col in df.columns:
                                    df[col] = pd.to_numeric(df[col], errors='coerce')
                            self.chains[date_str] = df
                    except Exception as e:
                        print(f"Warning: Could not load {filename}: {e}")
        
        self.dates = sorted(self.chains.keys())
        
        underlying_path = os.path.join(self.data_dir, 'arkk_underlying.csv')
        if os.path.exists(underlying_path):
            self.underlying = pd.read_csv(underlying_path)
            self.underlying['date'] = pd.to_datetime(self.underlying['date'])
        
        print(f"Loaded {len(self.chains)} option chain snapshots")
        if self.dates:
            print(f"Date range: {self.dates[0]} to {self.dates[-1]}")
    
    def get_dates(self):
        return self.dates
    
    def get_chain(self, date_str):
        return self.chains.get(date_str)
    
    def get_option(self, date_str, strike, expiration=None):
        chain = self.get_chain(date_str)
        if chain is None:
            return None
        if expiration is not None:
            chain = chain[chain['expiration'] == expiration]
        if chain.empty:
            return None
        
        # Drop rows where strike is NaN
        chain = chain.dropna(subset=['strike'])
        if chain.empty:
            return None
        
        row = chain[chain['strike'] == strike]
        if row.empty:
            distances = (chain['strike'] - strike).abs()
            nearest_idx = distances.idxmin()
            if distances[nearest_idx] <= 2.5:
                row = chain.loc[[nearest_idx]]
            else:
                return None
        
        row = row.iloc[0]
        return {
            'date': date_str,
            'strike': row['strike'],
            'bid': row.get('bid'),
            'ask': row.get('ask'),
            'mid': row.get('mid'),
            'iv': row.get('iv'),
            'delta': row.get('delta'),
            'gamma': row.get('gamma'),
            'theta': row.get('theta'),
            'vega': row.get('vega')
        }
    
    def get_underlying_price(self, date_str):
        if self.underlying is None:
            return None
        target = pd.to_datetime(date_str)
        exact = self.underlying[self.underlying['date'] == target]
        if not exact.empty:
            return round(float(exact.iloc[0]['close']), 2)
        prior = self.underlying[self.underlying['date'] <= target]
        if not prior.empty:
            nearest = prior.iloc[-1]
            if (target - nearest['date']).days <= 5:
                return round(float(nearest['close']), 2)
        future = self.underlying[self.underlying['date'] >= target]
        if not future.empty:
            nearest = future.iloc[0]
            if (nearest['date'] - target).days <= 5:
                return round(float(nearest['close']), 2)
        return None
    
    def get_strikes_near(self, date_str, target_price, otm_pct, n=3):
        chain = self.get_chain(date_str)
        if chain is None:
            return []
        chain = chain.dropna(subset=['strike'])
        target_strike = target_price * (1 - otm_pct)
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
                'iv': row.get('iv'),
                'delta': row.get('delta'),
                'gamma': row.get('gamma'),
                'theta': row.get('theta'),
                'vega': row.get('vega'),
                'otm_pct': round(1 - row['strike'] / target_price, 4)
            })
        return results
    
    def get_position_value(self, date_str, positions):
        total_value = 0
        total_delta = 0
        total_theta = 0
        total_vega = 0
        breakdown = []
        
        for pos in positions:
            opt = self.get_option(date_str, pos['strike'], pos.get('expiration'))
            if opt is None:
                breakdown.append({'strike': pos['strike'], 'contracts': pos['contracts'], 'status': 'NOT_FOUND'})
                continue
            qty = pos['contracts']
            mid = opt['mid']
            if mid is None or (isinstance(mid, float) and np.isnan(mid)):
                bid, ask = opt['bid'], opt['ask']
                if bid is not None and ask is not None:
                    try:
                        mid = round((float(bid) + float(ask)) / 2, 2)
                    except (ValueError, TypeError):
                        breakdown.append({'strike': pos['strike'], 'contracts': qty, 'status': 'NO_PRICE'})
                        continue
                else:
                    breakdown.append({'strike': pos['strike'], 'contracts': qty, 'status': 'NO_PRICE'})
                    continue
            value = float(mid) * qty * 100
            breakdown.append({
                'strike': opt['strike'], 'contracts': qty, 'bid': opt['bid'],
                'ask': opt['ask'], 'mid': mid, 'iv': opt.get('iv'),
                'delta': opt.get('delta'), 'value': value, 'status': 'OK'
            })
            total_value += value
            for greek_name in ['delta', 'theta', 'vega']:
                val = opt.get(greek_name)
                if val is not None:
                    try:
                        fval = float(val)
                        if not np.isnan(fval):
                            if greek_name == 'delta': total_delta += fval * qty * 100
                            elif greek_name == 'theta': total_theta += fval * qty * 100
                            elif greek_name == 'vega': total_vega += fval * qty * 100
                    except (ValueError, TypeError):
                        pass
        
        return {
            'date': date_str,
            'total_value': round(total_value, 2),
            'total_delta': round(total_delta, 2),
            'total_theta': round(total_theta, 2),
            'total_vega': round(total_vega, 2),
            'positions': breakdown
        }
    
    def summary(self):
        print(f"\n{'='*60}")
        print(f"ARKK OPTIONS DATA SUMMARY")
        print(f"{'='*60}")
        print(f"Snapshots loaded: {len(self.chains)}")
        if self.dates:
            print(f"Date range: {self.dates[0]} to {self.dates[-1]}")
        print(f"\nAvailable dates:")
        for d in self.dates:
            chain = self.chains[d]
            n = len(chain)
            valid = chain.dropna(subset=['strike'])
            smin = valid['strike'].min() if not valid.empty else 'N/A'
            smax = valid['strike'].max() if not valid.empty else 'N/A'
            price = self.get_underlying_price(d)
            p = f"  ARKK: ${price}" if price else ""
            print(f"  {d}  |  {n} strikes  |  ${smin} - ${smax}{p}")


if __name__ == '__main__':
    data = OptionsData()
    data.summary()
    
    print(f"\n{'='*60}")
    print("TEST: Entry positions (Oct 15, 2020)")
    print(f"{'='*60}")
    opt_80 = data.get_option('2020-10-15', 80)
    opt_65 = data.get_option('2020-10-15', 65)
    if opt_80:
        print(f"$80 Put: bid=${opt_80['bid']}, ask=${opt_80['ask']}, mid=${opt_80['mid']}, IV={opt_80['iv']}, delta={opt_80['delta']}")
    if opt_65:
        print(f"$65 Put: bid=${opt_65['bid']}, ask=${opt_65['ask']}, mid=${opt_65['mid']}, IV={opt_65['iv']}, delta={opt_65['delta']}")
    
    print(f"\n{'='*60}")
    print("TEST: Track $110 put (JAN 22) through available dates")
    print(f"{'='*60}")
    for d in data.get_dates():
        opt = data.get_option(d, 110, expiration='2022-01-21')
        if opt is None:
            opt = data.get_option(d, 110)
        price = data.get_underlying_price(d)
        if opt and opt['mid'] is not None:
            print(f"  {d}  |  ARKK: ${price or 'N/A':>8}  |  $110p mid: ${opt['mid']:>6}  |  IV: {opt['iv'] or 'N/A'}  |  delta: {opt['delta']}")
    
    print(f"\n{'='*60}")
    print("TEST: Track $110 put (JUL 22) from June 2021 onward")
    print(f"{'='*60}")
    for d in data.get_dates():
        if d >= '2021-06-17':
            opt = data.get_option(d, 110, expiration='2022-07-15')
            price = data.get_underlying_price(d)
            if opt and opt['mid'] is not None:
                print(f"  {d}  |  ARKK: ${price or 'N/A':>8}  |  $110p JUL22 mid: ${opt['mid']:>6}  |  IV: {opt['iv'] or 'N/A'}  |  delta: {opt['delta']}")