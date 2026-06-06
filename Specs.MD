# Project Specification: Solana Pump.fun Smart Money Tracker & Copy-Trading Analytics

## 1. Project Overview

You are building a data visualization and analytics web application designed to identify profitable wallets ("Smart Money") on the Solana Pump.fun platform. The goal is to help a user filter out bots, snipers, and insider clusters to safely allocate a 5,000 - 10,000 EUR capital into passive copy-trading strategies.

### Core Tech Stack:

- **Backend:** Python (FastAPI) or Node.js (TypeScript)
- **Database:** Neo4j (Graph Database) or Memgraph
- **Frontend:** React.js (Next.js) with TailwindCSS
- **Data Visualization Libraries:** `react-force-graph` (for network topologies), `recharts` or `chart.js` (for financial and operational charts)

---

## 2. Graph Database Schema (Neo4j)

The graph must be modeled to identify clusters and capital flows. Generate the database initialization scripts and optimization constraints (Indexes on addresses).

### Nodes:

- `TraderWallet` {address: String, label: String, win_rate: Float, total_profit_sol: Float}
- `PumpToken` {mint_address: String, ticker: String, status: String ("bonding" | "graduated")}
- `DeveloperWallet` {address: String}

### Relationships:

- `(:TraderWallet)-[:BOUGHT {timestamp: Integer, sol_amount: Float, token_amount: Float, position_index: Integer}]->(:PumpToken)`
- `(:TraderWallet)-[:SOLD {timestamp: Integer, sol_amount: Float, profit_usd: Float}]->(:PumpToken)`
- `(:DeveloperWallet)-[:CREATED]->(:PumpToken)`

---

## 3. Backend Pipelines & Data Processing (Python/Node)

Implement mock data generator or RPC extraction scripts that simulate Solana blockchain state changes.

### Critical Edge Cases to Handle in Data Processing:

1. **Developer Clusters (Sniper Bundles):** If a `DeveloperWallet` transfers SOL to multiple `TraderWallet` nodes, and all those nodes execute a `[:BOUGHT]` relation on the *same* `PumpToken` within the same block/millisecond, group them into an "Insider Cluster".
2. **Wash Trading (Volume Bots):** Detect ping-pong loops where `Wallet A` and `Wallet B` execute alternating Buy/Sell patterns within seconds. Filter these out from the "Smart Money" classification.
3. **Token Account Resolution:** Ensure that Solana Token Accounts (ATAs) are resolved back to their Main System Owner Address before creating graph nodes.

---

## 4. Frontend & Data Visualization Requirements

Create a responsive dashboard divided into 3 main functional views.

### View 1: Main Screener & Leaderboard

- A table listing identified "Smart Money" wallets.
- **Interactive UI Controls:**
  - Sliders for Minimum Win Rate (0-100%).
  - Slider for Minimum Profit (e.g., > 10 SOL).
  - Filter by Capital Size (to fit the 5k-10k EUR allocation, filtering out wallets trading with millions or pennies).

### View 2: Network Topology Explorer (The Graph)

- Implement a 2D/3D Force-Directed Graph using `react-force-graph`.
- **Visual Encoding:**
  - Center Node: Selected `PumpToken` or `TraderWallet`.
  - Edges (Muchii): Thickness scaled by transaction volume (`sol_amount`). Color: Green for buy, Red for sell.
  - Node Colors: Green = User/Trader, Red = DEX Contract, Yellow = Developer.
- **Interactivity:** Double-clicking a node must trigger a backend Cypher query to expand and fetch 2nd-degree neighbors.

### View 3: Portfolio ROI & Candlestick Overlay

- Line chart showcasing the historical net worth of a selected wallet.
- A candlestick chart of a token with overlayed markers (Green dots for `[:BOUGHT]` timestamps, Red dots for `[:SOLD]` timestamps) to visually judge the trader's entry/exit accuracy.

---

## 5. Algorithmic Insights & Analytics (The "Concluzii" Module)

Implement Cypher or backend algorithms to automatically tag wallets:

- **"Diamond Hands":** Average holding time > 24 hours.
- **"Paper Hands":** Sells at a loss within 5 minutes.
- **"Alpha Sniper":** Consistently buys in the first 3 position indexes of successful tokens.

### Simulation Engine (Sandbox Mode):

- Allow the user to input an investment amount (e.g., 500 EUR per trade) and run a backtest on the selected wallet's historical graph data to output expected ROI and maximum drawdown.
