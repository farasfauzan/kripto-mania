import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from learning_engine import *
import learning_engine

learning_engine.SIGNAL_LEARNING_DEDUPE_HOURS = 0
learning_engine.SIGNAL_LEARNING_TTL_HOURS = 72

def mock_entry_action(a): return True
passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name} {detail}")

for f in [SIGNAL_JOURNAL_FILE, SIGNAL_JOURNAL_FILE+".tmp"]:
    if os.path.exists(f): os.remove(f)

p = build_profile()
check("empty profile", p["total_signals"]==0 and p["winrate"] is None)

item = {"symbol":"BTCUSDT","action":"BUY","score":80,"allocation_pct":8,"confluence_passed":5,"entry":50000,"tp1":51000,"target":52000,"stop_loss":49000}
p = record_signal(item, mock_entry_action)
check("record signal total=1", p["total_signals"]==1)
check("record signal active=1", p["active"]==1)

p = record_signal(item, mock_entry_action)
check("dedupe open signal", p["total_signals"]==1 and p["active"]==1)

p = train_from_prices([{"symbol":"BTCUSDT","price":51500}])
check("train price no close", p["active"]==1)

p = train_from_prices([{"symbol":"BTCUSDT","price":52500}])
check("close TARGET WIN", p["active"]==0 and p["closed"]==1 and p["wins"]==1)

adj = apply_learning_adjustments([{"symbol":"BTCUSDT","score":50}], p)
check("no adj <3 trades", adj[0]["learning_adjustment"]==0 and adj[0]["learning_note"]=="Mengumpulkan data")

profile80 = {"by_symbol":{"BTCUSDT":{"closed":5,"wins":4,"losses":1,"winrate":80.0,"max_gain_sum":25.0,"avg_max_gain":5.0}}}
adj = apply_learning_adjustments([{"symbol":"BTCUSDT","score":50,"allocation_pct":5}], profile80)
check("80% WR adj=5", adj[0]["learning_adjustment"]==5)
check("80% WR score=55", adj[0]["score"]==55)
check("80% WR note", "Riwayat kuat" in adj[0]["learning_note"])

profile58 = {"by_symbol":{"A":{"closed":3,"wins":2,"losses":1,"winrate":66.7}}}
adj = apply_learning_adjustments([{"symbol":"A","score":50}], profile58)
check("58-69% WR adj=2", adj[0]["learning_adjustment"]==2)
check("58-69% WR note", "positif" in adj[0]["learning_note"])

profile38 = {"by_symbol":{"B":{"closed":3,"wins":1,"losses":2,"winrate":33.3}}}
adj = apply_learning_adjustments([{"symbol":"B","score":50}], profile38)
check("<=38% WR adj=-6", adj[0]["learning_adjustment"]==-6)
check("<=38% WR note", "lemah" in adj[0]["learning_note"])

profile49 = {"by_symbol":{"C":{"closed":3,"wins":1,"losses":2,"winrate":44.4}}}
adj = apply_learning_adjustments([{"symbol":"C","score":50}], profile49)
check("39-48% WR adj=-3", adj[0]["learning_adjustment"]==-3)

profile48 = {"by_symbol":{"D":{"closed":3,"wins":1,"losses":2,"winrate":50.0}}}
adj = apply_learning_adjustments([{"symbol":"D","score":50}], profile48)
check("49-57% WR adj=0", adj[0]["learning_adjustment"]==0)
check("49-57% WR note", "netral" in adj[0]["learning_note"])

item2 = {"symbol":"ETHUSDT","action":"SELL","score":70,"allocation_pct":6,"confluence_passed":4,"entry":3000,"tp1":2900,"target":2700,"stop_loss":3100}
p = record_signal(item2, mock_entry_action)
check("record SELL total=2", p["total_signals"]==2)
check("record SELL active=1 (ETH open, BTC closed)", p["active"]==1)

adj2 = apply_learning_adjustments([{"symbol":"BTCUSDT","score":98}], profile80)
check("score cap 100", adj2[0]["score"]==100)

adj3 = apply_learning_adjustments([{"symbol":"E","score":3,"allocation_pct":5}], {"by_symbol":{"E":{"closed":3,"wins":0,"losses":3,"winrate":0.0}}})
check("score floor 0", adj3[0]["score"]==0)

adj4 = apply_learning_adjustments([{"symbol":"BTCUSDT","score":50,"allocation_pct":5}], profile80)
check("alloc adj=6.0", adj4[0]["allocation_pct"]==6.0)

item3 = {"symbol":"XRPUSDT","action":"BUY","score":60,"allocation_pct":5,"confluence_passed":4,"entry":2.0,"tp1":2.05,"target":2.20,"stop_loss":1.90}
p = record_signal(item3, mock_entry_action)
p = train_from_prices([{"symbol":"XRPUSDT","price":2.07}])
check("TP1 hit stays OPEN", p["active"]==2)
learning_engine.SIGNAL_LEARNING_TTL_HOURS = 0
p = train_from_prices([{"symbol":"XRPUSDT","price":2.08}])
check("expire TP1=WIN", p["wins"]==2 and p["active"]==1)

learning_engine.SIGNAL_LEARNING_TTL_HOURS = 72
item4 = {"symbol":"SOLUSDT","action":"BUY","score":50,"allocation_pct":5,"confluence_passed":4,"entry":100,"tp1":105,"target":110,"stop_loss":95}
p = record_signal(item4, mock_entry_action)
p = train_from_prices([{"symbol":"SOLUSDT","price":99}])
print(f"DEBUG SOL active={p['active']} total={p['total_signals']} wins={p['wins']} closed={p['closed']}")
j = load_journal()
for s in j["signals"]:
    print(f"  {s['symbol']} status={s['status']} last_price={s.get('last_price')}")
check("SOL no TP1 active=2", p["active"]==2, f"got active={p['active']}")
p = train_from_prices([{"symbol":"SOLUSDT","price":101}])
learning_engine.SIGNAL_LEARNING_TTL_HOURS = 0
p = train_from_prices([{"symbol":"SOLUSDT","price":102}])
check("expire no TP1=LOSS", p["losses"]>=1 and p["active"]==1)

learning_engine.SIGNAL_LEARNING_TTL_HOURS = 72
item5 = {"symbol":"ADAUSDT","action":"BUY","score":70,"allocation_pct":5,"confluence_passed":4,"entry":0.5,"tp1":0.52,"target":0.58,"stop_loss":0.48}
p = record_signal(item5, mock_entry_action)
p = train_from_prices([{"symbol":"ADAUSDT","price":0.53}])
check("ADA TP1 hit", p["active"]==2)
p = train_from_prices([{"symbol":"ADAUSDT","price":0.47}])
check("SL with TP1=WIN", p["wins"]==3 and p["active"]==1)

j = load_journal()
p = build_profile(j)
# each symbol has <2 closed -> best_symbols empty
check("best_symbols empty (need >=2 per symbol)", len(p["best_symbols"])==0)
check("best_symbols format", all(len(x)==2 for x in p["best_symbols"]))

os.remove(SIGNAL_JOURNAL_FILE)
for f in [SIGNAL_JOURNAL_FILE+".tmp"]:
    if os.path.exists(f): os.remove(f)

print(f"\n=== {passed}/{passed+failed} tests passed ===")
sys.exit(0 if failed==0 else 1)
