// ==========================================
// 1. Schema Constraints & Indexes (Optimization)
// ==========================================

// Ensure addresses and mints are unique
CREATE CONSTRAINT UNIQUE_TRADER_WALLET FOR (w:TraderWallet) REQUIRE w.address IS UNIQUE;
CREATE CONSTRAINT UNIQUE_PUMP_TOKEN FOR (t:PumpToken) REQUIRE t.mint_address IS UNIQUE;
CREATE CONSTRAINT UNIQUE_DEV_WALLET FOR (d:DeveloperWallet) REQUIRE d.address IS UNIQUE;

// Create indexes for faster lookups
CREATE INDEX INDEX_TRADER_ADDRESS FOR (w:TraderWallet) ON (w.address);
CREATE INDEX INDEX_PUMP_MINT FOR (t:PumpToken) ON (t.mint_address);
CREATE INDEX INDEX_DEV_ADDRESS FOR (d:DeveloperWallet) ON (d.address);


// ==========================================
// 2. Algorithm Queries
// ==========================================

// Query 1: Developer Clusters (Sniper Bundles)
// Matches DeveloperWallet transfers SOL to multiple TraderWallets, 
// and those wallets execute BOUGHT on the same PumpToken within a 2-second window.
MATCH (dev:DeveloperWallet)-[:TRANSFERRED_SOL]->(w1:TraderWallet)-[b1:BOUGHT]->(token:PumpToken)
MATCH (dev)-[:TRANSFERRED_SOL]->(w2:TraderWallet)-[b2:BOUGHT]->(token)
WHERE w1 <> w2 AND abs(b1.timestamp - b2.timestamp) <= 2
RETURN dev.address AS developer, token.mint_address AS token_mint, collect(distinct w1.address) AS insider_wallets;


// Query 2: Wash Trading (Volume Bots)
// Detects ping-pong patterns: Wallet A and Wallet B alternating Buy/Sell sequences on the same token.
MATCH (w1:TraderWallet)-[b1:BOUGHT]->(t:PumpToken), (w1)-[s1:SOLD]->(t),
      (w2:TraderWallet)-[b2:BOUGHT]->(t), (w2)-[s2:SOLD]->(t)
WHERE w1.address < w2.address 
  AND b1.timestamp < b2.timestamp AND b2.timestamp < s1.timestamp AND s1.timestamp < s2.timestamp
WITH w1, w2, t, count(*) AS cycles
WHERE cycles >= 4
RETURN w1.address AS wash_trader_a, w2.address AS wash_trader_b, t.ticker AS token, cycles;


// Query 3: Persona Tagging - "Diamond Hands"
// Wallet holds tokens on average for more than 24 hours (86400 seconds)
MATCH (w:TraderWallet)-[b:BOUGHT]->(t:PumpToken), (w)-[s:SOLD]->(t)
WHERE s.timestamp > b.timestamp
WITH w, avg(s.timestamp - b.timestamp) AS avg_holding_time
WHERE avg_holding_time > 86400
SET w.tags = coalesce(w.tags, []) + "Diamond Hands"
RETURN w.address, avg_holding_time;


// Query 4: Persona Tagging - "Paper Hands"
// Sells at a loss within 5 minutes (300 seconds) of buying
MATCH (w:TraderWallet)-[b:BOUGHT]->(t:PumpToken), (w)-[s:SOLD]->(t)
WHERE s.timestamp > b.timestamp 
  AND (s.timestamp - b.timestamp) <= 300 
  AND s.profit_usd < 0
WITH w, count(s) AS panic_sells
WHERE panic_sells >= 1
SET w.tags = coalesce(w.tags, []) + "Paper Hands"
RETURN w.address, panic_sells;


// Query 5: Persona Tagging - "Alpha Sniper"
// Consistently buys in the first 3 position indexes of a token's lifecycle
MATCH (w:TraderWallet)-[b:BOUGHT]->(t:PumpToken)
WITH w, avg(b.position_index) AS avg_pos
WHERE avg_pos <= 3.0
SET w.tags = coalesce(w.tags, []) + "Alpha Sniper"
RETURN w.address, avg_pos;
