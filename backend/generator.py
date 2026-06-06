import random
import time
from typing import Dict, List, Any
from backend.graph_db import GraphDB

# Seed for reproducibility
random.seed(42)

def generate_solana_address(prefix: str = "") -> str:
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    length = 44 - len(prefix)
    return prefix + "".join(random.choice(chars) for _ in range(length))

def generate_mock_data(db: GraphDB):
    db.clear()
    
    # 1. Create Developer Wallets
    dev_wallets = [generate_solana_address("Dev") for _ in range(8)]
    for dev in dev_wallets:
        db.add_node(dev, "DeveloperWallet")

    # 2. Create Pump Tokens
    tickers = [
        "SOLCAT", "PUMPIN", "DOGGO", "FROG", "MOONAI", 
        "HYPE", "PUMPIT", "ROCKET", "AIX", "NEON", 
        "MEMEX", "ALPHA", "BULL", "BEAR", "SHIB2",
        "PUMPGO", "SPEED", "TURBO", "PEPE2", "GIGA"
    ]
    
    tokens = []
    token_price_histories: Dict[str, List[Dict[str, Any]]] = {}
    
    for i, ticker in enumerate(tickers):
        mint = generate_solana_address(f"Mint{ticker[:3]}")
        status = "graduated" if i < 12 else "bonding"
        token_node = db.add_node(mint, "PumpToken", {
            "mint_address": mint,
            "ticker": ticker,
            "status": status,
            "base_price": random.uniform(0.00001, 0.0001)  # in SOL
        })
        tokens.append(mint)
        
        # Link creator developer
        creator_dev = random.choice(dev_wallets)
        db.add_relationship(creator_dev, mint, "CREATED", {"timestamp": int(time.time()) - 86400 * 10})
        
        # Generate price history (candlesticks)
        # 48 hourly candles
        price_history = []
        current_time = int(time.time()) - 48 * 3600
        current_price = token_node.properties["base_price"]
        
        for hour in range(48):
            # Price trend based on graduated or bonding
            change = random.uniform(-0.15, 0.25) if status == "graduated" else random.uniform(-0.1, 0.12)
            # Add a pump peak for graduated tokens around middle hours
            if status == "graduated" and 15 < hour < 30:
                change += random.uniform(0.1, 0.5)
            
            open_p = current_price
            close_p = max(0.000001, current_price * (1 + change))
            high_p = max(open_p, close_p) * random.uniform(1.0, 1.15)
            low_p = min(open_p, close_p) * random.uniform(0.85, 1.0)
            
            price_history.append({
                "time": current_time,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": random.uniform(50, 1000)
            })
            current_price = close_p
            current_time += 3600
            
        token_price_histories[mint] = price_history
        token_node.properties["price_history"] = price_history
        token_node.properties["price_history_hourly"] = price_history
        
        # 120 minute candles representing the last 2 hours
        price_history_minutes = []
        min_current_time = int(time.time()) - 120 * 60
        # Start the minute price at the price from 2 hours ago (index 46 of hourly candles)
        min_current_price = price_history[46]["close"] if len(price_history) > 46 else token_node.properties["base_price"]
        
        for minute in range(120):
            change = random.uniform(-0.02, 0.025)
            open_p = min_current_price
            close_p = max(0.000001, min_current_price * (1 + change))
            high_p = max(open_p, close_p) * random.uniform(1.0, 1.03)
            low_p = min(open_p, close_p) * random.uniform(0.97, 1.0)
            
            price_history_minutes.append({
                "time": min_current_time,
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": random.uniform(2, 50)
            })
            min_current_price = close_p
            min_current_time += 60
            
        token_node.properties["price_history_minutes"] = price_history_minutes

    # 3. Create Trader Wallets (with persona labels)
    # We will generate 60 wallets in total, representing different behaviors
    
    traders = []
    
    # --- Category A: Alpha Snipers ---
    # High win rate, buy extremely early (position index 1-3), high profit, focus on minutes chart
    for i in range(10):
        addr = generate_solana_address("Snipe")
        wr = random.uniform(0.70, 0.92)
        prof = random.uniform(85.0, 320.0)
        db.add_node(addr, "TraderWallet", {
            "address": addr,
            "label": f"Alpha Sniper #{i+1}",
            "tags": ["Alpha Sniper"],
            "win_rate": wr,
            "total_profit_sol": prof,
            "capital_size_sol": random.uniform(15.0, 80.0),
            "timeframe_focus": "minutes",
            "win_rate_1m": wr + random.uniform(0.02, 0.08),
            "profit_sol_1m": prof * random.uniform(0.5, 0.7),
            "win_rate_1h": wr - random.uniform(0.05, 0.10),
            "profit_sol_1h": prof * random.uniform(0.3, 0.5)
        })
        traders.append((addr, "sniper"))
        
    # --- Category B: Diamond Hands ---
    # Long holding times (simulated via timestamp diff), decent win rate, medium-high profit, focus on hourly chart
    for i in range(12):
        addr = generate_solana_address("Dmd")
        wr = random.uniform(0.55, 0.75)
        prof = random.uniform(40.0, 180.0)
        db.add_node(addr, "TraderWallet", {
            "address": addr,
            "label": f"Diamond Hand #{i+1}",
            "tags": ["Diamond Hands"],
            "win_rate": wr,
            "total_profit_sol": prof,
            "capital_size_sol": random.uniform(10.0, 50.0),
            "timeframe_focus": "hourly",
            "win_rate_1m": wr - random.uniform(0.15, 0.25),
            "profit_sol_1m": prof * random.uniform(-0.1, 0.1),
            "win_rate_1h": wr + random.uniform(0.02, 0.08),
            "profit_sol_1h": prof * random.uniform(0.8, 0.95)
        })
        traders.append((addr, "diamond"))

    # --- Category C: Paper Hands ---
    # Sells very quickly (within minutes) at a loss, low win rate, negative profit, focus on minutes chart
    for i in range(12):
        addr = generate_solana_address("Paper")
        wr = random.uniform(0.15, 0.35)
        prof = random.uniform(-15.0, -2.0)
        db.add_node(addr, "TraderWallet", {
            "address": addr,
            "label": f"Paper Hand #{i+1}",
            "tags": ["Paper Hands"],
            "win_rate": wr,
            "total_profit_sol": prof,
            "capital_size_sol": random.uniform(5.0, 30.0),
            "timeframe_focus": "minutes",
            "win_rate_1m": wr,
            "profit_sol_1m": prof * random.uniform(0.8, 0.95),
            "win_rate_1h": wr + random.uniform(0.05, 0.1),
            "profit_sol_1h": prof * random.uniform(0.05, 0.2)
        })
        traders.append((addr, "paper"))

    # --- Category D: Wash Traders (Volume Bots) ---
    # Alternate buy/sell back and forth in seconds, zero/slightly negative profit, massive volume, focus on minutes
    wash_pairs = []
    for i in range(5):
        addr_a = generate_solana_address("WashA")
        addr_b = generate_solana_address("WashB")
        prof_a = random.uniform(-5.0, -1.0)
        prof_b = random.uniform(-5.0, -1.0)
        db.add_node(addr_a, "TraderWallet", {
            "address": addr_a,
            "label": f"Volume Bot A #{i+1}",
            "tags": ["Wash Trader"],
            "win_rate": 0.50,
            "total_profit_sol": prof_a,
            "capital_size_sol": random.uniform(100.0, 300.0),
            "timeframe_focus": "minutes",
            "win_rate_1m": 0.50,
            "profit_sol_1m": prof_a,
            "win_rate_1h": 0.50,
            "profit_sol_1h": prof_a
        })
        db.add_node(addr_b, "TraderWallet", {
            "address": addr_b,
            "label": f"Volume Bot B #{i+1}",
            "tags": ["Wash Trader"],
            "win_rate": 0.50,
            "total_profit_sol": prof_b,
            "capital_size_sol": random.uniform(100.0, 300.0),
            "timeframe_focus": "minutes",
            "win_rate_1m": 0.50,
            "profit_sol_1m": prof_b,
            "win_rate_1h": 0.50,
            "profit_sol_1h": prof_b
        })
        traders.append((addr_a, "wash"))
        traders.append((addr_b, "wash"))
        wash_pairs.append((addr_a, addr_b))

    # --- Category E: Insider Clusters (Developer Snipers) ---
    # A developer funds them, they buy same token within the same block/millisecond, focus on hourly
    insider_groups = []
    for i in range(3):
        dev_addr = dev_wallets[i]
        group = []
        for j in range(4):
            addr = generate_solana_address(f"InsG{i}W{j}")
            wr = random.uniform(0.75, 0.98)
            prof = random.uniform(150.0, 500.0)
            db.add_node(addr, "TraderWallet", {
                "address": addr,
                "label": f"Insider G{i+1} #{j+1}",
                "tags": ["Insider Cluster"],
                "win_rate": wr,
                "total_profit_sol": prof,
                "capital_size_sol": random.uniform(30.0, 150.0),
                "timeframe_focus": "hourly",
                "win_rate_1m": wr - random.uniform(0.1, 0.2),
                "profit_sol_1m": prof * random.uniform(0.2, 0.4),
                "win_rate_1h": wr,
                "profit_sol_1h": prof * random.uniform(0.8, 0.95)
            })
            traders.append((addr, "insider"))
            group.append(addr)
            # Fund relationship
            db.add_relationship(dev_addr, addr, "TRANSFERRED_SOL", {
                "timestamp": int(time.time()) - 86400 * 5,
                "sol_amount": random.uniform(5.0, 20.0)
            })
        insider_groups.append((dev_addr, group))

    # 4. Generate Relationships & Tx History
    start_time = int(time.time()) - 48 * 3600
    
    for token_mint in tokens:
        token_node = db.get_node(token_mint)
        status = token_node.properties["status"]
        candles = token_price_histories[token_mint]
        base_price = token_node.properties["base_price"]
        
        # Determine success of token (graduated tokens are successful, bonding are volatile)
        is_successful_token = (status == "graduated")
        
        # Position Index tracker
        position_index = 0
        
        # Snipers buy first (if successful token)
        if is_successful_token:
            snipers_buying = [t[0] for t in traders if t[1] == "sniper"]
            random.shuffle(snipers_buying)
            
            # First 3 snipers buy extremely early
            for sniper in snipers_buying[:3]:
                # Buy
                buy_time = start_time + random.randint(10, 60)
                sol_amt = random.uniform(1.5, 4.0)
                token_price = base_price * random.uniform(1.0, 1.05)
                tok_amt = sol_amt / token_price
                
                db.add_relationship(sniper, token_mint, "BOUGHT", {
                    "timestamp": buy_time,
                    "sol_amount": sol_amt,
                    "token_amount": tok_amt,
                    "position_index": position_index,
                    "price": token_price
                })
                
                # Sell near the peak (middle of price candles)
                # Middle candles are indexes 20 to 25
                sell_candle = candles[random.randint(20, 25)]
                sell_time = sell_candle["time"]
                sell_price = sell_candle["high"] * random.uniform(0.9, 1.0)
                sell_sol_amt = tok_amt * sell_price
                profit_usd = (sell_sol_amt - sol_amt) * 150.0  # Assumes 1 SOL = 150 USD/EUR
                
                db.add_relationship(sniper, token_mint, "SOLD", {
                    "timestamp": sell_time,
                    "sol_amount": sell_sol_amt,
                    "profit_usd": profit_usd,
                    "price": sell_price
                })
                
                position_index += 1

        # Insider Clusters execution
        # Let's say group 0 buys token 0, group 1 buys token 3, group 2 buys token 6
        for group_idx, (dev_addr, group_wallets) in enumerate(insider_groups):
            target_token_idx = group_idx * 3
            if target_token_idx < len(tokens):
                target_token = tokens[target_token_idx]
                insider_buy_time = start_time + 120 # Same timestamp/block
                
                for wallet in group_wallets:
                    sol_amt = random.uniform(5.0, 15.0)
                    token_price = base_price * random.uniform(1.01, 1.03)
                    tok_amt = sol_amt / token_price
                    
                    db.add_relationship(wallet, target_token, "BOUGHT", {
                        "timestamp": insider_buy_time,
                        "sol_amount": sol_amt,
                        "token_amount": tok_amt,
                        "position_index": position_index,
                        "price": token_price
                    })
                    position_index += 1
                    
                    # Sells at graduation (candle index 40)
                    sell_candle = candles[40]
                    sell_time = sell_candle["time"]
                    sell_price = sell_candle["close"] * random.uniform(0.95, 1.05)
                    sell_sol_amt = tok_amt * sell_price
                    profit_usd = (sell_sol_amt - sol_amt) * 150.0
                    
                    db.add_relationship(wallet, target_token, "SOLD", {
                        "timestamp": sell_time,
                        "sol_amount": sell_sol_amt,
                        "profit_usd": profit_usd,
                        "price": sell_price
                    })

        # Diamond Hands transactions
        dmd_traders = [t[0] for t in traders if t[1] == "diamond"]
        for dmd in dmd_traders:
            # Chooses 2-3 random tokens
            chosen_tokens = random.sample(tokens, random.randint(2, 3))
            for t_mint in chosen_tokens:
                # Buys around candle 5
                buy_candle = candles[random.randint(2, 6)]
                buy_time = buy_candle["time"]
                sol_amt = random.uniform(2.0, 8.0)
                token_price = buy_candle["close"]
                tok_amt = sol_amt / token_price
                
                db.add_relationship(dmd, t_mint, "BOUGHT", {
                    "timestamp": buy_time,
                    "sol_amount": sol_amt,
                    "token_amount": tok_amt,
                    "position_index": random.randint(10, 30),
                    "price": token_price
                })
                
                # Sells after 24+ hours (at least 24 candles later)
                # If token is successful, holds and makes profit. If not, holds and sells at minor profit/loss.
                sell_idx = random.randint(27, 45)
                sell_candle = candles[sell_idx]
                sell_time = sell_candle["time"]
                sell_price = sell_candle["close"]
                sell_sol_amt = tok_amt * sell_price
                profit_usd = (sell_sol_amt - sol_amt) * 150.0
                
                db.add_relationship(dmd, t_mint, "SOLD", {
                    "timestamp": sell_time,
                    "sol_amount": sell_sol_amt,
                    "profit_usd": profit_usd,
                    "price": sell_price
                })

        # Paper Hands transactions
        paper_traders = [t[0] for t in traders if t[1] == "paper"]
        for paper in paper_traders:
            chosen_tokens = random.sample(tokens, random.randint(2, 4))
            for t_mint in chosen_tokens:
                # Buys during peak or volatile candles
                buy_idx = random.randint(10, 25)
                buy_candle = candles[buy_idx]
                buy_time = buy_candle["time"]
                sol_amt = random.uniform(1.0, 5.0)
                token_price = buy_candle["high"] * random.uniform(0.98, 1.02)
                tok_amt = sol_amt / token_price
                
                db.add_relationship(paper, t_mint, "BOUGHT", {
                    "timestamp": buy_time,
                    "sol_amount": sol_amt,
                    "token_amount": tok_amt,
                    "position_index": random.randint(25, 60),
                    "price": token_price
                })
                
                # Panic sells 2 to 5 minutes later (simulated within the same hour/candle or next candle)
                # Sells at a loss
                sell_time = buy_time + random.randint(120, 300)
                sell_price = token_price * random.uniform(0.75, 0.90)  # 10-25% loss
                sell_sol_amt = tok_amt * sell_price
                profit_usd = (sell_sol_amt - sol_amt) * 150.0
                
                db.add_relationship(paper, t_mint, "SOLD", {
                    "timestamp": sell_time,
                    "sol_amount": sell_sol_amt,
                    "profit_usd": profit_usd,
                    "price": sell_price
                })

        # Wash Traders / Volume Bots transactions
        # Ping pong alternating Buy/Sell loops
        for pair_idx, (addr_a, addr_b) in enumerate(wash_pairs):
            # Target a specific token for each pair
            target_token = tokens[pair_idx % len(tokens)]
            pair_start_time = start_time + 3600 * 2
            
            # Perform 15 alternating cycles
            for cycle in range(15):
                # Wallet A Buys
                a_buy_time = pair_start_time + cycle * 120
                sol_amt = random.uniform(15.0, 25.0)
                token_price = candles[2]["close"] * random.uniform(0.99, 1.01)
                tok_amt = sol_amt / token_price
                db.add_relationship(addr_a, target_token, "BOUGHT", {
                    "timestamp": a_buy_time,
                    "sol_amount": sol_amt,
                    "token_amount": tok_amt,
                    "position_index": 50 + cycle * 2,
                    "price": token_price
                })
                
                # Wallet A Sells to B / DEX (A Sells, B Buys)
                a_sell_time = a_buy_time + random.randint(10, 20)
                sell_price = token_price * 0.998  # Tiny fee loss
                a_sell_sol = tok_amt * sell_price
                db.add_relationship(addr_a, target_token, "SOLD", {
                    "timestamp": a_sell_time,
                    "sol_amount": a_sell_sol,
                    "profit_usd": (a_sell_sol - sol_amt) * 150.0,
                    "price": sell_price
                })
                
                # Wallet B Buys
                b_buy_time = a_sell_time + 5
                db.add_relationship(addr_b, target_token, "BOUGHT", {
                    "timestamp": b_buy_time,
                    "sol_amount": a_sell_sol,
                    "token_amount": tok_amt,
                    "position_index": 51 + cycle * 2,
                    "price": sell_price
                })
                
                # Wallet B Sells
                b_sell_time = b_buy_time + random.randint(10, 20)
                b_sell_sol = tok_amt * sell_price * 0.998
                db.add_relationship(addr_b, target_token, "SOLD", {
                    "timestamp": b_sell_time,
                    "sol_amount": b_sell_sol,
                    "profit_usd": (b_sell_sol - a_sell_sol) * 150.0,
                    "price": sell_price * 0.998
                })

    # 5. Compute Net Worth Over Time (Historical Equity Curve)
    # For every trader wallet, we generate historical net worth points (24 data points representing the last 24h/48h)
    for wallet_id, node in db.nodes.items():
        if node.type == "TraderWallet":
            # Generate a realistic equity curve based on total profit
            total_profit = node.properties.get("total_profit_sol", 0.0)
            capital = node.properties.get("capital_size_sol", 20.0)
            
            history = []
            current_capital = capital
            step_profit = total_profit / 24.0
            
            cur_time = int(time.time()) - 24 * 3600
            for h in range(25):
                # Add minor fluctuations
                fluctuation = random.uniform(-1.5, 1.5)
                # If they are wash traders, their capital slowly degrades
                if "Wash Trader" in node.properties.get("tags", []):
                    current_capital -= 0.1
                else:
                    current_capital += step_profit + fluctuation
                
                current_capital = max(0.5, current_capital)
                history.append({
                    "time": cur_time,
                    "equity": round(current_capital, 2),
                    "equity_eur": round(current_capital * 150.0, 2)
                })
                cur_time += 3600
                
            node.properties["equity_history"] = history

    print(f"Database loaded successfully: {len(db.nodes)} nodes, and thousands of relationships created.")
