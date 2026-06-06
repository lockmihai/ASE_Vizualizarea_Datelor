from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import os

from backend.graph_db import GraphDB
from backend.generator import generate_mock_data
from backend.predictor import TimesFMPredictor
from backend.algorithms import (
    detect_insider_clusters,
    detect_wash_trading,
    run_roi_simulation,
    resolve_token_account
)

app = FastAPI(title="Solana Pump.fun Tracker API")

# Initialize TimesFM Predictor
predictor = TimesFMPredictor()

# Allow CORS for local dev environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global Graph database and load mock data
db = GraphDB()
generate_mock_data(db)

# Run detection algorithms once at startup (or dynamically)
# Store cache to keep it fast
insider_clusters = detect_insider_clusters(db)
wash_traders = detect_wash_trading(db)

# Apply tags dynamically to database nodes based on calculations
for dev_token, members in insider_clusters.items():
    dev_addr, token_mint = dev_token.split(":")
    for member in members:
        node = db.get_node(member)
        if node and "Insider Cluster" not in node.properties["tags"]:
            node.properties["tags"].append("Insider Cluster")
            node.properties["insider_group"] = dev_token

for wash in wash_traders:
    node = db.get_node(wash)
    if node and "Wash Trader" not in node.properties["tags"]:
        node.properties["tags"].append("Wash Trader")

# Dynamic Persona Tagging as per requirements:
# - "Diamond Hands": Average holding time > 24 hours (modeled during generation)
# - "Paper Hands": Sells at a loss within 5 minutes (modeled during generation)
# - "Alpha Sniper": Consistently buys in first 3 positions (modeled during generation)
for wallet_id, node in db.nodes.items():
    if node.type == "TraderWallet":
        # Calculate a simulated position index average
        buys = [rel for tgt, rel in db.out_edges.get(wallet_id, []) if rel.type == "BOUGHT"]
        if buys:
            avg_position = sum(b.properties.get("position_index", 99) for b in buys) / len(buys)
            if avg_position <= 3.0 and "Alpha Sniper" not in node.properties["tags"]:
                node.properties["tags"].append("Alpha Sniper")

class BacktestRequest(BaseModel):
    wallet_id: str
    investment_amount: float
    strategy: str  # 'exact_copy' | 'fixed_per_trade' | 'fixed_percent'
    sol_rate: float = 150.0

@app.get("/api/screener")
def get_screener(
    min_win_rate: float = 0.0,
    min_profit: float = 0.0,
    min_capital: float = 0.0,
    max_capital: float = 100000.0,
    exclude_wash: bool = False
):
    """
    Returns lists of smart money wallets filtered by criteria.
    """
    results = []
    for addr, node in db.nodes.items():
        if node.type != "TraderWallet":
            continue
            
        props = node.properties
        win_rate = props.get("win_rate", 0.0)
        profit = props.get("total_profit_sol", 0.0)
        capital = props.get("capital_size_sol", 0.0)
        tags = props.get("tags", [])
        
        # Filter rules
        if win_rate < min_win_rate:
            continue
        if profit < min_profit:
            continue
        if capital < min_capital or capital > max_capital:
            continue
        if exclude_wash and "Wash Trader" in tags:
            continue
            
        results.append({
            "address": addr,
            "label": props.get("label", "Unknown Wallet"),
            "win_rate": round(win_rate * 100, 1),
            "total_profit_sol": round(profit, 2),
            "capital_size_sol": round(capital, 2),
            "tags": tags
        })
        
    # Sort by profit descending
    results.sort(key=lambda x: x["total_profit_sol"], reverse=True)
    return results

@app.get("/api/graph/explore")
def explore_graph(center_node: Optional[str] = None):
    """
    Returns a graph snippet for rendering.
    If center_node is provided, returns its 2nd-degree neighbors.
    Otherwise, returns a beautiful default subset of the active market.
    """
    if center_node:
        # Resolve token account if needed
        resolved_center = resolve_token_account(center_node)
        nodes, rels = db.get_second_degree_neighbors(resolved_center)
        return {"nodes": nodes, "links": rels}
        
    # Return a default active subset (e.g. 3 graduated tokens, their creators, and top traders)
    default_nodes = []
    default_rels = []
    visited = set()
    
    # Select 3 graduated tokens
    tokens = [addr for addr, node in db.nodes.items() if node.type == "PumpToken" and node.properties.get("status") == "graduated"][:3]
    
    for token in tokens:
        if token not in visited:
            visited.add(token)
            default_nodes.append(db.get_node(token).to_dict())
            
        # Get relationships for this token
        # Creator developer
        for source_id, rel in db.in_edges.get(token, []):
            if rel.type == "CREATED":
                if source_id not in visited:
                    visited.add(source_id)
                    default_nodes.append(db.get_node(source_id).to_dict())
                default_rels.append(rel.to_dict())
                
        # Limit to top 5 traders per token to keep default graph clean and readable
        trader_count = 0
        for source_id, rel in db.in_edges.get(token, []):
            if rel.type in ("BOUGHT", "SOLD") and trader_count < 5:
                if source_id not in visited:
                    visited.add(source_id)
                    default_nodes.append(db.get_node(source_id).to_dict())
                default_rels.append(rel.to_dict())
                trader_count += 1
                
    return {"nodes": default_nodes, "links": default_rels}

@app.get("/api/wallet/{address}")
def get_wallet(address: str):
    resolved = resolve_token_account(address)
    node = db.get_node(resolved)
    if not node or node.type != "TraderWallet":
        raise HTTPException(status_code=404, detail="Wallet not found")
        
    # Compute active trades count
    buys = len([r for t, r in db.out_edges.get(resolved, []) if r.type == "BOUGHT"])
    sells = len([r for t, r in db.out_edges.get(resolved, []) if r.type == "SOLD"])
    
    return {
        "address": resolved,
        "label": node.properties.get("label", "Unknown Trader"),
        "win_rate": round(node.properties.get("win_rate", 0.0) * 100, 1),
        "total_profit_sol": round(node.properties.get("total_profit_sol", 0.0), 2),
        "capital_size_sol": round(node.properties.get("capital_size_sol", 0.0), 2),
        "tags": node.properties.get("tags", []),
        "equity_history": node.properties.get("equity_history", []),
        "trade_stats": {
            "buys": buys,
            "sells": sells,
            "total_trades": buys + sells
        }
    }

@app.get("/api/token/{mint}")
def get_token(mint: str, resolution: str = "1h"):
    node = db.get_node(mint)
    if not node or node.type != "PumpToken":
        raise HTTPException(status_code=404, detail="Token not found")
        
    price_key = "price_history_minutes" if resolution == "1m" else "price_history_hourly"
    price_history = node.properties.get(price_key, node.properties.get("price_history", []))
    
    return {
        "mint_address": mint,
        "ticker": node.properties.get("ticker", "UNKNOWN"),
        "status": node.properties.get("status", "bonding"),
        "price_history": price_history
    }

@app.get("/api/token/{mint}/trades/{wallet_id}")
def get_token_trades(mint: str, wallet_id: str):
    """
    Returns list of buys and sells by a specific wallet on a specific token.
    Used for overlaying execution dots on the candlestick chart.
    """
    resolved_wallet = resolve_token_account(wallet_id)
    trades = []
    
    # Scan relationships
    for target_id, rel in db.out_edges.get(resolved_wallet, []):
        if target_id == mint and rel.type in ("BOUGHT", "SOLD"):
            trades.append({
                "type": rel.type,
                "timestamp": rel.properties.get("timestamp"),
                "price": rel.properties.get("price"),
                "sol_amount": rel.properties.get("sol_amount"),
                "token_amount": rel.properties.get("token_amount")
            })
            
    return trades

@app.post("/api/simulation/backtest")
def post_backtest(req: BacktestRequest):
    result = run_roi_simulation(
        db=db,
        wallet_id=req.wallet_id,
        investment_amount_eur=req.investment_amount,
        strategy=req.strategy,
        sol_rate=req.sol_rate
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

# In-memory copy trading database state
copy_trading_portfolio = {
    "enabled": False,
    "total_balance_eur": 5000.0,
    "max_allocation_per_trade_eur": 500.0,
    "stop_loss_pct": -15.0,
    "take_profit_pct": 50.0,
    "followed_wallets": {}, # wallet_address -> dict of settings
}

# Active positions state
# Each position: {id, wallet_address, token_mint, ticker, size_eur, entry_price, current_price, entry_time, last_update_time, profit_loss_eur, status ("open" | "closed"), exit_reason (None | "TP" | "SL" | "TRADER_EXIT"), roi_pct}
simulated_positions = []
next_trade_id = 1
simulation_clock = int(time.time()) - 48 * 3600 # Sync with generator start_time

class FollowWalletRequest(BaseModel):
    wallet_address: str
    label: str
    enabled: bool = True
    custom_allocation_eur: Optional[float] = None

class CopyTradeSettingsRequest(BaseModel):
    enabled: bool
    total_balance_eur: float
    max_allocation_per_trade_eur: float
    stop_loss_pct: float
    take_profit_pct: float

@app.get("/api/crawler/run")
def run_crawler(timeframe: str = Query("1m", pattern="^(1m|1h)$")):
    """
    Simulates crawling the Solana blockchain for wallets that perform well on timeframe (1m or 1h).
    """
    results = []
    target_focus = "minutes" if timeframe == "1m" else "hourly"
    
    for addr, node in db.nodes.items():
        if node.type != "TraderWallet":
            continue
        
        props = node.properties
        focus = props.get("timeframe_focus", "both")
        if focus != target_focus and focus != "both":
            continue
            
        # Fetch timeframe specific metrics
        win_rate = props.get(f"win_rate_{timeframe}", props.get("win_rate", 0.0))
        profit = props.get(f"profit_sol_{timeframe}", props.get("total_profit_sol", 0.0))
        capital = props.get("capital_size_sol", 0.0)
        tags = props.get("tags", [])
        
        # Only return profitable ones for the crawler to represent "top accounts"
        if profit > 0:
            results.append({
                "address": addr,
                "label": props.get("label", "Unknown Wallet"),
                "win_rate": round(win_rate * 100, 1),
                "total_profit_sol": round(profit, 2),
                "capital_size_sol": round(capital, 2),
                "timeframe_focus": focus,
                "tags": tags
            })
            
    # Sort by profit descending
    results.sort(key=lambda x: x["total_profit_sol"], reverse=True)
    return {
        "status": "success",
        "scanned_wallets": 14205,
        "timeframe": timeframe,
        "wallets_found": len(results),
        "results": results
    }

@app.get("/api/copytrade/config")
def get_copytrade_config():
    return copy_trading_portfolio

@app.post("/api/copytrade/config")
def post_copytrade_config(req: CopyTradeSettingsRequest):
    copy_trading_portfolio["enabled"] = req.enabled
    copy_trading_portfolio["total_balance_eur"] = req.total_balance_eur
    copy_trading_portfolio["max_allocation_per_trade_eur"] = req.max_allocation_per_trade_eur
    copy_trading_portfolio["stop_loss_pct"] = req.stop_loss_pct
    copy_trading_portfolio["take_profit_pct"] = req.take_profit_pct
    return {"status": "success", "config": copy_trading_portfolio}

@app.post("/api/copytrade/follow")
def post_copytrade_follow(req: FollowWalletRequest):
    addr = resolve_token_account(req.wallet_address)
    node = db.get_node(addr)
    if not node or node.type != "TraderWallet":
        raise HTTPException(status_code=404, detail="Wallet to follow not found")
        
    copy_trading_portfolio["followed_wallets"][addr] = {
        "address": addr,
        "label": req.label,
        "enabled": req.enabled,
        "custom_allocation_eur": req.custom_allocation_eur
    }
    return {"status": "success", "followed": copy_trading_portfolio["followed_wallets"][addr]}

@app.delete("/api/copytrade/follow/{address}")
def delete_copytrade_follow(address: str):
    addr = resolve_token_account(address)
    if addr in copy_trading_portfolio["followed_wallets"]:
        del copy_trading_portfolio["followed_wallets"][addr]
        return {"status": "success", "message": f"Stopped following {address}"}
    raise HTTPException(status_code=404, detail="Followed wallet not found")

@app.get("/api/copytrade/positions")
def get_copytrade_positions():
    return {
        "balance_eur": round(copy_trading_portfolio["total_balance_eur"], 2),
        "positions": simulated_positions
    }

@app.post("/api/copytrade/tick")
def post_copytrade_tick():
    """
    Progresses the simulation clock by 1 minute, simulates copy-trading execution.
    - Scans followed wallets' historical trades.
    - If a followed wallet executed a BUY at a timestamp that aligns with our clock, we open a copy position.
    - If a followed wallet executed a SELL at a timestamp, or if we hit SL/TP, we close the position.
    - Fluctuate open positions' current price based on the token's price history at that timestamp.
    """
    global simulation_clock, next_trade_id
    
    # Progress clock by 1 minute (60 seconds)
    simulation_clock += 60
    
    if not copy_trading_portfolio["enabled"]:
        return {
            "status": "simulation_idle",
            "simulation_time": simulation_clock,
            "message": "Copy-trading is disabled. Enable copy-trading in the Settings panel."
        }
        
    # Fetch followed active wallets
    followed_addresses = [addr for addr, w in copy_trading_portfolio["followed_wallets"].items() if w["enabled"]]
    
    new_events = []
    
    # 1. Update existing open positions
    for pos in simulated_positions:
        if pos["status"] != "open":
            continue
            
        # Fetch the token node to find current price
        token_mint = pos["token_mint"]
        token_node = db.get_node(token_mint)
        if not token_node:
            continue
            
        # Find close price matching the current simulation time from minutes or hourly price history
        price_history = token_node.properties.get("price_history_minutes", [])
        current_price = pos["entry_price"]
        
        # Find closest candle in time
        matching_candles = [c for c in price_history if c["time"] <= simulation_clock]
        if matching_candles:
            current_price = matching_candles[-1]["close"]
        else:
            # Fallback to hourly price history
            h_history = token_node.properties.get("price_history_hourly", [])
            matching_h = [c for c in h_history if c["time"] <= simulation_clock]
            if matching_h:
                current_price = matching_h[-1]["close"]
                
        # Update price and ROI
        pos["current_price"] = current_price
        roi = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
        pos["roi_pct"] = round(roi, 2)
        pos["profit_loss_eur"] = round(pos["size_eur"] * (roi / 100.0), 2)
        pos["last_update_time"] = simulation_clock
        
        # Check SL/TP exit conditions
        sl = copy_trading_portfolio["stop_loss_pct"]
        tp = copy_trading_portfolio["take_profit_pct"]
        
        if roi <= sl:
            pos["status"] = "closed"
            pos["exit_reason"] = "SL"
            pos["exit_time"] = simulation_clock
            copy_trading_portfolio["total_balance_eur"] += pos["size_eur"] + pos["profit_loss_eur"]
            new_events.append(f"Position on {pos['ticker']} closed via Stop Loss at {pos['roi_pct']}% PnL")
        elif roi >= tp:
            pos["status"] = "closed"
            pos["exit_reason"] = "TP"
            pos["exit_time"] = simulation_clock
            copy_trading_portfolio["total_balance_eur"] += pos["size_eur"] + pos["profit_loss_eur"]
            new_events.append(f"Position on {pos['ticker']} closed via Take Profit at {pos['roi_pct']}% PnL")
            
    # 2. Scan for new trades from followed wallets matching the simulation time
    for wallet in followed_addresses:
        wallet_node = db.get_node(wallet)
        if not wallet_node:
            continue
            
        # Check outgoing BOUGHT relationships
        for target_id, rel in db.out_edges.get(wallet, []):
            if rel.type == "BOUGHT":
                tx_time = rel.properties.get("timestamp", 0)
                # If the wallet bought a token within the last simulated minute (60s)
                if simulation_clock - 60 < tx_time <= simulation_clock:
                    # Ensure we aren't already copy-trading this token for this wallet
                    already_open = any(p["status"] == "open" and p["wallet_address"] == wallet and p["token_mint"] == target_id for p in simulated_positions)
                    if not already_open:
                        wallet_settings = copy_trading_portfolio["followed_wallets"][wallet]
                        size = wallet_settings.get("custom_allocation_eur") or copy_trading_portfolio["max_allocation_per_trade_eur"]
                        size = min(size, copy_trading_portfolio["total_balance_eur"])
                        
                        if size > 10.0:
                            # Subtract capital
                            copy_trading_portfolio["total_balance_eur"] -= size
                            
                            token_node = db.get_node(target_id)
                            ticker = token_node.properties.get("ticker", "UNKNOWN") if token_node else "UNKNOWN"
                            
                            new_pos = {
                                "id": next_trade_id,
                                "wallet_address": wallet,
                                "wallet_label": wallet_settings["label"],
                                "token_mint": target_id,
                                "ticker": ticker,
                                "size_eur": round(size, 2),
                                "entry_price": rel.properties.get("price", 0.0001),
                                "current_price": rel.properties.get("price", 0.0001),
                                "entry_time": tx_time,
                                "last_update_time": simulation_clock,
                                "profit_loss_eur": 0.0,
                                "roi_pct": 0.0,
                                "status": "open",
                                "exit_reason": None
                            }
                            simulated_positions.append(new_pos)
                            next_trade_id += 1
                            new_events.append(f"Copy trade opened for {ticker} (allocated {size} EUR)")
                            
            elif rel.type == "SOLD":
                tx_time = rel.properties.get("timestamp", 0)
                if simulation_clock - 60 < tx_time <= simulation_clock:
                    for pos in simulated_positions:
                        if pos["status"] == "open" and pos["wallet_address"] == wallet and pos["token_mint"] == target_id:
                            pos["status"] = "closed"
                            pos["exit_reason"] = "TRADER_EXIT"
                            pos["exit_time"] = tx_time
                            pos["current_price"] = rel.properties.get("price", pos["current_price"])
                            roi = ((pos["current_price"] - pos["entry_price"]) / pos["entry_price"]) * 100
                            pos["roi_pct"] = round(roi, 2)
                            pos["profit_loss_eur"] = round(pos["size_eur"] * (roi / 100.0), 2)
                            copy_trading_portfolio["total_balance_eur"] += pos["size_eur"] + pos["profit_loss_eur"]
                            new_events.append(f"Position on {pos['ticker']} closed (Trader exited trade) at {pos['roi_pct']}% PnL")
                            
    return {
        "status": "success",
        "simulation_time": simulation_clock,
        "events": new_events,
        "balance_eur": round(copy_trading_portfolio["total_balance_eur"], 2),
        "open_positions_count": len([p for p in simulated_positions if p["status"] == "open"])
    }

@app.post("/api/admin/reset")
def post_reset():
    """Reset and regenerate database"""
    generate_mock_data(db)
    global insider_clusters, wash_traders, simulated_positions, next_trade_id, simulation_clock
    insider_clusters = detect_insider_clusters(db)
    wash_traders = detect_wash_trading(db)
    
    # Reset simulation state
    copy_trading_portfolio["total_balance_eur"] = 5000.0
    copy_trading_portfolio["followed_wallets"].clear()
    simulated_positions.clear()
    next_trade_id = 1
    simulation_clock = int(time.time()) - 48 * 3600
    
    return {"status": "success", "message": "Database and copy-trading simulation reset."}

@app.get("/api/token/{mint}/prediction")
def get_token_prediction(
    mint: str,
    resolution: str = Query("1h", pattern="^(1m|1h)$"),
    horizon: Optional[int] = None
):
    node = db.get_node(mint)
    if not node or node.type != "PumpToken":
        raise HTTPException(status_code=404, detail="Token not found")
        
    price_key = "price_history_minutes" if resolution == "1m" else "price_history_hourly"
    price_history = node.properties.get(price_key, [])
    if not price_history:
        raise HTTPException(status_code=400, detail="No price history found for this token")

    # Extract closing prices
    close_prices = [candle["close"] for candle in price_history]
    
    # Choose default horizon if not provided
    if horizon is None:
        horizon = 30 if resolution == "1m" else 12
        
    # Run prediction
    prediction_result = predictor.forecast(close_prices, horizon=horizon)
    
    return {
        "mint_address": mint,
        "ticker": node.properties.get("ticker", "UNKNOWN"),
        "resolution": resolution,
        "horizon": horizon,
        "history": price_history,
        "predictions": prediction_result
    }

# Serve React frontend static files
static_path = "/app/static" if os.path.exists("/app/static") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../static")
if not os.path.exists(static_path):
    static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../frontend/dist")

if os.path.exists(static_path):
    app.mount("/", StaticFiles(directory=static_path, html=True), name="static")
else:
    print(f"Warning: static files directory not found at {static_path}. React app will not be served.")
