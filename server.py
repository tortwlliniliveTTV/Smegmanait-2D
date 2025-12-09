import socket
from _thread import *
import pickle
import math
import time
import random

SERVER_IP = ""
PORT = 5555

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind((SERVER_IP, PORT))
except socket.error as e:
    print(str(e))

s.listen(4)
print("--- TITAN SERVER V10.1 (STABLE) ---")

players = {}
walls = [] 
map_objects = []
current_id = 0
winner_id = None
restart_ts = 0

storm = { "center": (2000, 2000), "radius": 3000, "active": False }

WEAPONS = {
    'Pickaxe':{'speed': 0, 'damage': 10, 'range': 60,  'struct_dmg': 50},
    'Pistol': {'speed': 15,'damage': 15, 'range': 600, 'struct_dmg': 10},
    'SMG':    {'speed': 18,'damage': 8,  'range': 400, 'struct_dmg': 5},
    'Sniper': {'speed': 40,'damage': 95, 'range': 1200,'struct_dmg': 80}
}

def generate_map_objects():
    global map_objects
    map_objects = []
    for _ in range(100):
        map_objects.append({'type':'tree', 'x':random.randint(200,3800), 'y':random.randint(200,3800), 'hp':100, 'r':25})
    for _ in range(50):
        map_objects.append({'type':'rock', 'x':random.randint(200,3800), 'y':random.randint(200,3800), 'hp':300, 'w':40, 'h':40})

generate_map_objects()

def reset_match():
    global players, walls, storm, winner_id
    print("MATCH RESET!")
    walls = []
    generate_map_objects()
    storm["radius"] = 3000
    storm["active"] = True
    winner_id = None
    
    for pid in players:
        players[pid]["x"] = random.randint(1500, 2500)
        players[pid]["y"] = random.randint(1500, 2500)
        players[pid]["hp"] = 100
        players[pid]["is_dead"] = False
        players[pid]["spectating"] = None
        players[pid]["wood"] = 0

def update_storm():
    if not storm["active"]: return
    # La tempesta parte solo se ci sono almeno 2 giocatori
    if len(players) < 2: return 

    if storm["radius"] > 200: storm["radius"] -= 0.5
    
    alive = [pid for pid in players if not players[pid]["is_dead"]]
    for pid in alive:
        dist = math.hypot(players[pid]["x"] - storm["center"][0], players[pid]["y"] - storm["center"][1])
        if dist > storm["radius"]:
            players[pid]["hp"] -= 0.5
            if players[pid]["hp"] <= 0:
                players[pid]["hp"] = 0
                players[pid]["is_dead"] = True

def check_winner():
    global winner_id, restart_ts
    
    # FIX: Non controllare vittoria se c'è un solo giocatore nel server (Sandbox Mode)
    if len(players) < 2: 
        return

    alive = [pid for pid in players if not players[pid]["is_dead"]]
    
    # Se ne resta solo 1 VIVO
    if len(alive) == 1 and winner_id is None:
        winner_id = alive[0]
        restart_ts = time.time() + 8
        print(f"WINNER: P-{winner_id}")

    if winner_id is not None and time.time() > restart_ts:
        reset_match()

def threaded_client(conn, p_id):
    global players, walls, map_objects
    
    colors = [(0,150,255), (255,50,50), (50,255,50), (255,255,0)]
    
    # FIX: Spawn Randomico alla connessione (non più 2000, 2000)
    start_x = random.randint(1000, 3000)
    start_y = random.randint(1000, 3000)

    players[p_id] = {
        "x": start_x, "y": start_y, "color": colors[p_id % len(colors)],
        "hp": 100, "weapon": "Pickaxe", "bullets": [], "wood": 0,
        "is_dead": False, "spectating": None
    }
    conn.send(pickle.dumps(p_id))
    storm["active"] = True

    while True:
        try:
            data = pickle.loads(conn.recv(16384))
            if not data: break
            
            if not players[p_id]["is_dead"] and winner_id is None:
                players[p_id]["x"] = data["x"]
                players[p_id]["y"] = data["y"]
                players[p_id]["weapon"] = data["weapon"]

                if data["build"] and players[p_id]["wood"] >= 10:
                    bx, by = (data["x"] // 50) * 50, (data["y"] // 50) * 50
                    if not any(w['x'] == bx and w['y'] == by for w in walls):
                        walls.append({'x': bx, 'y': by, 'hp': 100})
                        players[p_id]["wood"] -= 10

                if data["shoot"]:
                    stats = WEAPONS[data["weapon"]]
                    angle = data["angle"]
                    players[p_id]["bullets"].append({
                        "x": players[p_id]["x"]+16, "y": players[p_id]["y"]+16,
                        "dx": math.cos(angle)*stats['speed'] if stats['speed']>0 else math.cos(angle)*10,
                        "dy": math.sin(angle)*stats['speed'] if stats['speed']>0 else math.sin(angle)*10,
                        "trav": 0, "range": stats['range'], 
                        "dmg": stats['damage'], "struct_dmg": stats['struct_dmg'],
                        "type": "melee" if stats['speed'] == 0 else "bullet"
                    })

            # FISICA
            my_bullets = players[p_id]["bullets"]
            for b in my_bullets[:]:
                b["x"] += b["dx"]
                b["y"] += b["dy"]
                b["trav"] += math.hypot(b["dx"], b["dy"])
                
                if b["trav"] > b["range"]:
                    my_bullets.remove(b); continue

                hit = False
                for w in walls[:]:
                    if w['x'] < b["x"] < w['x']+50 and w['y'] < b["y"] < w['y']+50:
                        w['hp'] -= b["struct_dmg"]
                        if w['hp'] <= 0: walls.remove(w)
                        hit = True; break
                
                if not hit:
                    for obj in map_objects[:]:
                        if obj['type'] == 'tree':
                            if math.hypot(b["x"] - obj['x'], b["y"] - obj['y']) < obj['r']:
                                obj['hp'] -= b["struct_dmg"]
                                if obj['hp'] <= 0:
                                    map_objects.remove(obj)
                                    players[p_id]["wood"] += 30
                                hit = True; break
                        elif obj['type'] == 'rock':
                             if obj['x'] < b['x'] < obj['x']+40 and obj['y'] < b['y'] < obj['y']+40:
                                obj['hp'] -= b["struct_dmg"]
                                if obj['hp'] <= 0: map_objects.remove(obj)
                                hit = True; break

                if not hit:
                    for oid in players:
                        if oid != p_id and not players[oid]["is_dead"]:
                            ox, oy = players[oid]["x"], players[oid]["y"]
                            if ox < b["x"] < ox+32 and oy < b["y"] < oy+32:
                                players[oid]["hp"] -= b["dmg"]
                                if players[oid]["hp"] <= 0:
                                    players[oid]["is_dead"] = True
                                    players[oid]["spectating"] = p_id
                                hit = True; break
                
                if hit: my_bullets.remove(b)

            if p_id == 0: 
                update_storm()
                check_winner()

            game_state = {
                "players": players, "walls": walls, "objects": map_objects,
                "storm": storm, "winner": winner_id
            }
            conn.sendall(pickle.dumps(game_state))

        except Exception as e:
            break

    del players[p_id]
    conn.close()

while True:
    conn, addr = s.accept()
    start_new_thread(threaded_client, (conn, current_id))
    current_id += 1