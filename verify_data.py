from data_loader import OptionsData
data = OptionsData()

print("\n" + "="*80)
print("DATA VERIFICATION — ALL DATES")
print("="*80)

for d in data.get_dates():
    chain = data.get_chain(d)
    arkk = data.get_underlying_price(d)
    n = len(chain) if chain is not None else 0
    
    # Get expirations
    exps = []
    if chain is not None and 'expiration' in chain.columns:
        exps = sorted(chain['expiration'].dropna().unique())
    
    # Try looking up a few key strikes for each expiration
    lookups = []
    for exp in exps:
        sub = chain[chain['expiration'] == exp]
        valid = sub.dropna(subset=['strike', 'bid'])
        n_valid = len(valid)
        strike_min = valid['strike'].min() if not valid.empty else 'N/A'
        strike_max = valid['strike'].max() if not valid.empty else 'N/A'
        
        # Try $90 and $110 strikes
        for test_strike in [90, 110]:
            opt = data.get_option(d, test_strike, exp)
            if opt and opt['mid'] is not None:
                lookups.append(str(exp)[-5:] + " $" + str(test_strike) + "p=" + str(opt['mid']))
    
    exp_str = " | ".join([str(e) for e in exps])
    lookup_str = "  ".join(lookups) if lookups else "NO LOOKUPS"
    
    flag = ""
    if n == 0:
        flag = " *** EMPTY ***"
    elif not lookups:
        flag = " *** NO VALID LOOKUPS ***"
    
    print(d + " | ARKK: $" + str(arkk or 'N/A').ljust(8) + " | " + str(n).rjust(3) + " rows | " + exp_str + " | " + lookup_str + flag)