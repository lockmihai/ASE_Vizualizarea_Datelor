import collections
import time
from typing import Dict, List, Set, Tuple, Any
from backend.graph_db import GraphDB

def resolve_token_account(address: str) -> str:
    """
    Simulates resolving a Solana Associated Token Account (ATA) back to the Owner wallet address.
    If the address is prepended with 'ATA_', we extract the owner address portion.
    """
    if address.startswith("ATA_"):
        # e.g., ATA_Dmd7238... -> Dmd7238...
        return address[4:]
    return address

def detect_insider_clusters(db: GraphDB) -> Dict[str, List[str]]:
    """
    Identifies 'Insider Clusters':
    - DeveloperWallet transfers SOL to multiple TraderWallets.
    - Those TraderWallets execute a 'BOUGHT' relation on the SAME PumpToken within 2 seconds of each other.
    Returns: Dict mapping DeveloperWallet -> List of TraderWallet addresses in the cluster.
    """
    clusters = collections.defaultdict(list)
    
    # Let's find all DeveloperWallets
    dev_wallets = [addr for addr, node in db.nodes.items() if node.type == "DeveloperWallet"]
    
    for dev in dev_wallets:
        # Find all wallets funded by this dev
        transfers = db.out_edges.get(dev, [])
        funded_wallets = []
        for target_id, rel in transfers:
            if rel.type == "TRANSFERRED_SOL":
                funded_wallets.append(target_id)
                
        if not funded_wallets:
            continue
            
        # Check if these funded wallets bought the same token at the same time
        # Let's collect all buys for these funded wallets
        wallet_buys: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for wallet in funded_wallets:
            for target_id, rel in db.out_edges.get(wallet, []):
                if rel.type == "BOUGHT":
                    wallet_buys[wallet].append({
                        "token": target_id,
                        "timestamp": rel.properties.get("timestamp", 0),
                        "position_index": rel.properties.get("position_index", 0)
                    })
        
        # Group buys by token
        token_buys = collections.defaultdict(list)
        for wallet, buys in wallet_buys.items():
            for buy in buys:
                token_buys[buy["token"]].append((wallet, buy["timestamp"]))
                
        # Find clusters where multiple wallets bought the same token within 2 seconds
        for token, buys in token_buys.items():
            # Pairwise compare timestamps
            cluster_members = set()
            for i in range(len(buys)):
                for j in range(i + 1, len(buys)):
                    w1, t1 = buys[i]
                    w2, t2 = buys[j]
                    if abs(t1 - t2) <= 2:  # 2 seconds window
                        cluster_members.add(w1)
                        cluster_members.add(w2)
                        
            if len(cluster_members) >= 2:
                clusters[f"{dev}:{token}"] = list(cluster_members)
                
    return clusters

def detect_wash_trading(db: GraphDB) -> Set[str]:
    """
    Identifies 'Wash Trading' (Volume Bots):
    - Wallet A and Wallet B executing alternating Buy/Sell patterns (ping-pong) within a short window.
    - If a wallet pair has >= 4 alternating transaction sequences on the same token.
    Returns: Set of TraderWallet addresses tagged as Wash Traders.
    """
    wash_traders = set()
    
    # Group trades by (wallet, token)
    wallet_token_trades = collections.defaultdict(list)
    for wallet_id, node in db.nodes.items():
        if node.type != "TraderWallet":
            continue
        
        for target_id, rel in db.out_edges.get(wallet_id, []):
            if rel.type in ("BOUGHT", "SOLD"):
                wallet_token_trades[(wallet_id, target_id)].append({
                    "type": rel.type,
                    "timestamp": rel.properties.get("timestamp", 0)
                })
                
    # Sort trades by timestamp
    for key in wallet_token_trades:
        wallet_token_trades[key].sort(key=lambda x: x["timestamp"])
        
    # Find ping-pong pairs
    all_keys = list(wallet_token_trades.keys())
    for i in range(len(all_keys)):
        for j in range(i + 1, len(all_keys)):
            w1, t1 = all_keys[i]
            w2, t2 = all_keys[j]
            
            if t1 != t2:  # Must be same token
                continue
                
            trades1 = wallet_token_trades[(w1, t1)]
            trades2 = wallet_token_trades[(w2, t2)]
            
            # Check if there's alternating temporal overlap
            merged_trades = []
            for t in trades1:
                merged_trades.append((w1, t["type"], t["timestamp"]))
            for t in trades2:
                merged_trades.append((w2, t["type"], t["timestamp"]))
            
            merged_trades.sort(key=lambda x: x[2])
            
            # Count alternating patterns between w1 and w2
            alternations = 0
            last_wallet = None
            last_type = None
            
            for wallet, tx_type, timestamp in merged_trades:
                if last_wallet is not None:
                    # If different wallet and alternating action or complementary action
                    if wallet != last_wallet and tx_type != last_type:
                        alternations += 1
                last_wallet = wallet
                last_type = tx_type
                
            if alternations >= 8:  # Significant alternating volume loop
                wash_traders.add(w1)
                wash_traders.add(w2)
                
    return wash_traders

def run_roi_simulation(
    db: GraphDB,
    wallet_id: str,
    investment_amount_eur: float,
    strategy: str = "exact_copy",
    sol_rate: float = 150.0
) -> Dict[str, Any]:
    """
    Simulates copy-trading a selected wallet's historical performance.
    
    Parameters:
    - investment_amount_eur: Capital allocated to start trading.
    - strategy:
      - 'exact_copy': Scale trade sizes based on the wallet's actual SOL sizes relative to its start capital.
      - 'fixed_per_trade': Trade a fixed amount (e.g. 500 EUR) on every token.
      - 'fixed_percent': Trade a fixed % of current portfolio on every token.
    - sol_rate: Exchange rate (1 SOL = X EUR).
    """
    trader_node = db.get_node(wallet_id)
    if not trader_node:
        return {"error": "Wallet not found"}

    # Gather all buys and sells for this trader
    buys = []
    sells = []
    
    for target_id, rel in db.out_edges.get(wallet_id, []):
        if rel.type == "BOUGHT":
            buys.append({
                "token": target_id,
                "timestamp": rel.properties.get("timestamp", 0),
                "sol_amount": rel.properties.get("sol_amount", 0.0),
                "token_amount": rel.properties.get("token_amount", 0.0),
                "price": rel.properties.get("price", 0.0)
            })
        elif rel.type == "SOLD":
            sells.append({
                "token": target_id,
                "timestamp": rel.properties.get("timestamp", 0),
                "sol_amount": rel.properties.get("sol_amount", 0.0),
                "profit_usd": rel.properties.get("profit_usd", 0.0),
                "price": rel.properties.get("price", 0.0)
            })

    # Match buys and sells by token
    trades: List[Dict[str, Any]] = []
    
    # Simple FIFO/Match
    for buy in buys:
        token = buy["token"]
        # Find corresponding sell
        matching_sells = [s for s in sells if s["token"] == token and s["timestamp"] > buy["timestamp"]]
        if matching_sells:
            # Sort sells and take the closest one
            matching_sells.sort(key=lambda x: x["timestamp"])
            sell = matching_sells[0]
            
            # Compute ROI metrics
            profit_sol = sell["sol_amount"] - buy["sol_amount"]
            roi_pct = (profit_sol / buy["sol_amount"]) * 100 if buy["sol_amount"] > 0 else 0.0
            
            trades.append({
                "token": token,
                "buy_time": buy["timestamp"],
                "sell_time": sell["timestamp"],
                "buy_price": buy["price"],
                "sell_price": sell["price"],
                "sol_amount": buy["sol_amount"],
                "profit_sol": profit_sol,
                "roi_pct": roi_pct
            })

    # Sort trades chronologically by buy time
    trades.sort(key=lambda x: x["buy_time"])

    # Simulate portfolio balances
    portfolio_value = investment_amount_eur
    portfolio_history = [{"timestamp": int(time.time()) - 48*3600, "balance": portfolio_value}]
    
    max_portfolio_val = portfolio_value
    max_drawdown = 0.0
    successful_trades = 0
    
    sim_trades = []
    
    for trade in trades:
        # Determine size of trade in EUR
        if strategy == "fixed_per_trade":
            trade_size_eur = min(portfolio_value, 500.0) # Cap at current portfolio
        elif strategy == "fixed_percent":
            trade_size_eur = portfolio_value * 0.10 # 10% allocation
        else: # 'exact_copy'
            # Estimate allocation based on wallet's scale
            wallet_capital = trader_node.properties.get("capital_size_sol", 20.0) * sol_rate
            allocation_ratio = (trade["sol_amount"] * sol_rate) / wallet_capital if wallet_capital > 0 else 0.1
            trade_size_eur = min(portfolio_value, portfolio_value * allocation_ratio)

        # Skip trade if we have no balance left
        if trade_size_eur <= 0.01:
            continue
            
        profit_ratio = trade["roi_pct"] / 100.0
        profit_eur = trade_size_eur * profit_ratio
        
        portfolio_value += profit_eur
        
        # Calculate success
        is_success = profit_eur > 0
        if is_success:
            successful_trades += 1
            
        sim_trades.append({
            "token": trade["token"],
            "ticker": db.get_node(trade["token"]).properties.get("ticker", "UNKNOWN"),
            "buy_time": trade["buy_time"],
            "sell_time": trade["sell_time"],
            "allocated_eur": round(trade_size_eur, 2),
            "profit_eur": round(profit_eur, 2),
            "roi_pct": round(trade["roi_pct"], 2),
            "success": is_success
        })
        
        portfolio_history.append({
            "timestamp": trade["sell_time"],
            "balance": round(portfolio_value, 2)
        })
        
        # Drawdown calculation
        if portfolio_value > max_portfolio_val:
            max_portfolio_val = portfolio_value
        else:
            drawdown = ((max_portfolio_val - portfolio_value) / max_portfolio_val) * 100.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    expected_roi = ((portfolio_value - investment_amount_eur) / investment_amount_eur) * 100 if investment_amount_eur > 0 else 0

    return {
        "wallet_id": wallet_id,
        "strategy": strategy,
        "initial_capital_eur": investment_amount_eur,
        "final_capital_eur": round(portfolio_value, 2),
        "expected_roi_pct": round(expected_roi, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "success_rate": round((successful_trades / len(sim_trades) * 100), 2) if sim_trades else 0.0,
        "trades_executed": len(sim_trades),
        "sim_trades": sim_trades,
        "equity_curve": portfolio_history
    }
