import pygame
import socket
import pickle
import math
import sys
import copy

# --- CONFIGURAZIONE ---
SERVER = "localhost" # CAMBIA IP SE GIOCHI CON AMICI (es. "192.168.1.X")
PORT = 5555

SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 768
FPS = 60

# Colori (I tuoi colori personalizzati)
GRASS_COLOR = (46, 139, 87)
PLAYER_COLOR = (0, 150, 255)
ENEMY_COLOR = (220, 20, 60)
WOOD_COLOR = (139, 69, 19)
STONE_COLOR = (105, 105, 105)
AMMO_COLOR = (255, 215, 0)
WEAPON_COLOR = (255, 0, 255)
STORM_ZONE_COLOR = (138, 43, 226)
UI_BG_COLOR = (30, 30, 30, 180)
DAMAGE_TEXT_COLOR = (255, 255, 255)
CRIT_TEXT_COLOR = (255, 50, 50)
TREE_COLOR = (0, 100, 0)
ROCK_COLOR = (80, 80, 80)
GOLD = (255, 215, 0)

# --- CLASSE DI RETE ---
class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addr = (SERVER, PORT)
        self.p_id = self.connect()

    def connect(self):
        try:
            self.client.connect(self.addr)
            return pickle.loads(self.client.recv(4096))
        except:
            print("ERRORE: Impossibile connettersi al Server.")
            return None

    def send(self, data):
        try:
            self.client.send(pickle.dumps(data))
            # Buffer grande per ricevere mappa e giocatori
            return pickle.loads(self.client.recv(32768)) 
        except socket.error as e:
            print(e)
            return None

# --- CLASSI VISIVE (TUE) ---
class FloatingText:
    def __init__(self, x, y, text, color, size=20):
        self.x = x
        self.y = y
        self.text = str(text)
        self.color = color
        self.life = 60 
        self.y_offset = 0
        self.font = pygame.font.SysFont("Arial", size, bold=True)

    def update(self):
        self.life -= 1
        self.y_offset -= 1 

    def draw(self, screen, camera):
        if self.life > 0:
            alpha = min(255, self.life * 5)
            surf = self.font.render(self.text, True, self.color)
            surf.set_alpha(alpha)
            # Applica offset camera
            screen_pos = camera.apply_pos(self.x, self.y + self.y_offset)
            screen.blit(surf, screen_pos)

class KillFeed:
    def __init__(self):
        self.messages = [] 
    
    def add_message(self, text):
        self.messages.append([text, 300])
        if len(self.messages) > 5:
            self.messages.pop(0)

    def update_and_draw(self, screen):
        font = pygame.font.SysFont("Arial", 14)
        y = 50
        for msg in self.messages[:]:
            msg[1] -= 1
            if msg[1] <= 0:
                self.messages.remove(msg)
                continue
            
            text_surf = font.render(msg[0], True, (255, 255, 255))
            bg_surf = pygame.Surface((text_surf.get_width() + 10, text_surf.get_height() + 4))
            bg_surf.fill((0,0,0))
            bg_surf.set_alpha(150)
            
            x_pos = SCREEN_WIDTH - text_surf.get_width() - 20
            screen.blit(bg_surf, (x_pos - 5, y - 2))
            screen.blit(text_surf, (x_pos, y))
            y += 25

class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0

    def update(self, target_x, target_y):
        # Lerp per fluidità
        self.x += (target_x - SCREEN_WIDTH // 2 - self.x) * 0.1
        self.y += (target_y - SCREEN_HEIGHT // 2 - self.y) * 0.1

    def apply(self, rect):
        return pygame.Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)
    
    def apply_pos(self, x, y):
        return (x - self.x, y - self.y)

# --- CLASSE PLAYER LOCALE (INPUT) ---
class PlayerLocal:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 32, 32)
        self.speed = 5
        self.inventory = ['Pickaxe', 'Pistol', 'SMG', 'Sniper'] 
        self.current_weapon_idx = 0
        self.current_weapon = 'Pickaxe'
        self.cooldown = 0

    def move(self):
        keys = pygame.key.get_pressed()
        dx, dy = 0, 0
        if keys[pygame.K_w]: dy = -self.speed
        if keys[pygame.K_s]: dy = self.speed
        if keys[pygame.K_a]: dx = -self.speed
        if keys[pygame.K_d]: dx = self.speed
        if dx!=0 and dy!=0: dx*=0.707; dy*=0.707
        self.rect.x += dx
        self.rect.y += dy

    def get_input_data(self):
        keys = pygame.key.get_pressed()
        
        # Cambio arma
        if keys[pygame.K_1]: self.current_weapon_idx = 0
        if keys[pygame.K_2]: self.current_weapon_idx = 1
        if keys[pygame.K_3]: self.current_weapon_idx = 2
        if keys[pygame.K_4]: self.current_weapon_idx = 3
        self.current_weapon = self.inventory[self.current_weapon_idx]

        if self.cooldown > 0: self.cooldown -= 1
        
        mouse = pygame.mouse.get_pressed()
        shoot = False
        build = False
        
        # Click Sinistro (Sparo/Picconata)
        if mouse[0] and self.cooldown <= 0:
            shoot = True
            # Cooldown client-side per feedback visivo
            cd_map = {'Pickaxe': 15, 'Pistol': 20, 'SMG': 5, 'Sniper': 60}
            self.cooldown = cd_map.get(self.current_weapon, 20)
            
        # Click Destro (Costruzione)
        if mouse[2]: 
            build = True

        mx, my = pygame.mouse.get_pos()
        # Angolo rispetto al centro dello schermo (visto che la camera è centrata sul player)
        angle = math.atan2(my - SCREEN_HEIGHT//2, mx - SCREEN_WIDTH//2)

        return {
            "x": self.rect.x,
            "y": self.rect.y,
            "weapon": self.current_weapon,
            "shoot": shoot,
            "build": build,
            "angle": angle
        }

# --- GIOCO PRINCIPALE ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Fortnite 2D - CLIENT ONLINE V10")
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.font = pygame.font.SysFont("Verdana", 16)
        self.ui_font = pygame.font.SysFont("Verdana", 12, bold=True)
        self.font_win = pygame.font.SysFont("Impact", 80)
        
        # Networking
        self.n = Network()
        
        # Sistemi
        self.camera = Camera()
        self.kill_feed = KillFeed()
        self.floating_texts = []
        
        # Player Locale (inizialmente a 0,0, verrà teletrasportato dal server)
        self.player_local = PlayerLocal(0, 0)
        self.init_pos_set = False # Per gestire lo spawn iniziale
        
        # Memoria per calcolare danni (Floating Text)
        self.prev_players_state = {} 

        self.game_over = False

    def run(self):
        if self.n.p_id is None:
            return # Esce se non connesso

        while True:
            self.clock.tick(FPS)
            
            # 1. Eventi Pygame
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            # 2. Input e Movimento Locale
            self.player_local.move()
            data_to_send = self.player_local.get_input_data()

            # 3. Networking (Invia Input -> Ricevi Stato Mondo)
            server_state = self.n.send(data_to_send)
            
            if not server_state:
                continue # Salta frame se pacchetto perso

            # Estrai dati dal server
            players = server_state["players"]
            walls = server_state["walls"]
            objects = server_state["objects"] # Alberi e Rocce
            storm = server_state["storm"]
            winner = server_state["winner"]

            # 4. Aggiornamenti Logici Client-Side
            my_stats = players.get(self.n.p_id)
            
            if my_stats:
                # Setup posizione iniziale (Spawn)
                if not self.init_pos_set:
                    self.player_local.rect.x = my_stats["x"]
                    self.player_local.rect.y = my_stats["y"]
                    self.init_pos_set = True
                
                # Gestione Camera
                if not my_stats["is_dead"]:
                    self.camera.update(self.player_local.rect.x, self.player_local.rect.y)
                elif my_stats["spectating"] in players:
                    # Spettatore
                    target = players[my_stats["spectating"]]
                    self.camera.update(target["x"], target["y"])

                # --- LOGICA DEL "JUICE" (Floating Text & Kill Feed) ---
                # Confrontiamo lo stato attuale con quello precedente per vedere danni e morti
                for pid, p in players.items():
                    if pid in self.prev_players_state:
                        prev = self.prev_players_state[pid]
                        
                        # Rileva Danno
                        diff = prev['hp'] - p['hp']
                        if diff > 0.5: # Ignora piccoli arrotondamenti
                            color = CRIT_TEXT_COLOR if diff > 20 else DAMAGE_TEXT_COLOR
                            txt = f"-{int(diff)}"
                            self.floating_texts.append(FloatingText(p['x'], p['y'], txt, color))
                        
                        # Rileva Morte (Killfeed)
                        if p['is_dead'] and not prev['is_dead']:
                             victim = "YOU" if pid == self.n.p_id else f"P-{pid}"
                             self.kill_feed.add_message(f"{victim} ELIMINATED")

                self.prev_players_state = copy.deepcopy(players)

            # 5. Disegno (Rendering)
            self.draw(players, walls, objects, storm, winner, my_stats)
            
            pygame.display.flip()

    def draw(self, players, walls, objects, storm, winner, my_stats):
        self.screen.fill(GRASS_COLOR)
        
        # Griglia
        gx = int(self.camera.x // 100) * 100
        gy = int(self.camera.y // 100) * 100
        for x in range(gx - 100, gx + SCREEN_WIDTH + 100, 100):
            xx = x - self.camera.x
            pygame.draw.line(self.screen, (30,120,50), (xx,0), (xx,SCREEN_HEIGHT))
        for y in range(gy - 100, gy + SCREEN_HEIGHT + 100, 100):
            yy = y - self.camera.y
            pygame.draw.line(self.screen, (30,120,50), (0,yy), (SCREEN_WIDTH,yy))

        # Disegna Oggetti Mappa (Alberi/Rocce dal Server V10)
        for obj in objects:
            if obj['type'] == 'tree':
                pos = self.camera.apply_pos(obj['x'], obj['y'])
                pygame.draw.circle(self.screen, (0,50,0), (int(pos[0])+2, int(pos[1])+2), obj['r']) # Ombra
                pygame.draw.circle(self.screen, TREE_COLOR, (int(pos[0]), int(pos[1])), obj['r'])
                # Barra HP albero
                if obj['hp'] < 100:
                    pygame.draw.rect(self.screen, (200,0,0), (pos[0]-15, pos[1]-5, 30, 4))
                    pygame.draw.rect(self.screen, (0,200,0), (pos[0]-15, pos[1]-5, 30*(obj['hp']/100), 4))
            elif obj['type'] == 'rock':
                r = pygame.Rect(obj['x'], obj['y'], obj['w'], obj['h'])
                pygame.draw.rect(self.screen, ROCK_COLOR, self.camera.apply(r))

        # Disegna Muri
        for w in walls:
            r = self.camera.apply(pygame.Rect(w['x'], w['y'], 50, 50))
            pygame.draw.rect(self.screen, WOOD_COLOR, r)
            pygame.draw.rect(self.screen, (0,0,0), r, 2)
            # Effetto danno muro
            if w['hp'] < 100:
                 pygame.draw.line(self.screen, (0,0,0), (r.x, r.y), (r.bottomright[0], r.bottomright[1]), 2)

        # Disegna Giocatori
        for pid, p in players.items():
            if p["is_dead"]: continue
            
            r = self.camera.apply(pygame.Rect(p['x'], p['y'], 32, 32))
            
            # Disegna solo se nello schermo
            if -50 < r.x < SCREEN_WIDTH+50 and -50 < r.y < SCREEN_HEIGHT+50:
                pygame.draw.rect(self.screen, p['color'], r)
                
                # Piccone o Arma
                if p['weapon'] == 'Pickaxe':
                    pygame.draw.line(self.screen, (80,80,80), (r.centerx, r.centery), (r.centerx+15, r.centery-10), 4)
                
                # HP Bar
                perc = max(0, p['hp'] / 100)
                pygame.draw.rect(self.screen, (255,0,0), (r.x, r.y-10, 32, 5))
                pygame.draw.rect(self.screen, (0,255,0), (r.x, r.y-10, 32*perc, 5))
                
                # Nome
                lbl = "YOU" if pid == self.n.p_id else f"P-{pid}"
                screen_txt = self.font.render(lbl, True, (255,255,255))
                self.screen.blit(screen_txt, (r.x, r.y-25))

        # Disegna Proiettili
        for p in players.values():
            for b in p['bullets']:
                bp = self.camera.apply_pos(b['x'], b['y'])
                col = (255,255,0) if b.get('type', 'bullet') == 'bullet' else (255,255,255)
                rad = 4 if b.get('type', 'bullet') == 'bullet' else 2
                pygame.draw.circle(self.screen, col, (int(bp[0]), int(bp[1])), rad)

        # Disegna Tempesta
        sc = self.camera.apply_pos(storm['center'][0], storm['center'][1])
        pygame.draw.circle(self.screen, STORM_ZONE_COLOR, (int(sc[0]), int(sc[1])), int(storm['radius']), 4)
        
        # Overlay Danno Tempesta
        dist = math.hypot(self.player_local.rect.x - storm['center'][0], self.player_local.rect.y - storm['center'][1])
        if dist > storm['radius']:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(50)
            overlay.fill(STORM_ZONE_COLOR)
            self.screen.blit(overlay, (0,0))
            warn = self.font.render("! IN STORM !", True, (255,255,255))
            self.screen.blit(warn, (SCREEN_WIDTH//2-50, 60))

        # Floating Texts
        for ft in self.floating_texts[:]:
            ft.update()
            if ft.life <= 0: self.floating_texts.remove(ft)
            else: ft.draw(self.screen, self.camera)

        # UI Overlay (HUD)
        if my_stats and not my_stats["is_dead"]:
            # Materiali
            wood_txt = self.ui_font.render(f"WOOD: {my_stats['wood']}", True, GOLD)
            pygame.draw.rect(self.screen, (0,0,0), (10, SCREEN_HEIGHT-40, 120, 30))
            self.screen.blit(wood_txt, (20, SCREEN_HEIGHT-35))

            # Inventario
            inv_w, inv_h = 50, 50
            start_x = SCREEN_WIDTH//2 - (len(self.player_local.inventory) * (inv_w+5)) // 2
            
            for i, item in enumerate(self.player_local.inventory):
                rect = pygame.Rect(start_x + i*(inv_w+5), SCREEN_HEIGHT - 70, inv_w, inv_h)
                col = GOLD if i == self.player_local.current_weapon_idx else (50, 50, 50)
                pygame.draw.rect(self.screen, col, rect)
                pygame.draw.rect(self.screen, (200,200,200), rect, 2)
                
                name = item[:2] if item != 'Pickaxe' else 'PK'
                txt = self.ui_font.render(name, True, (255,255,255) if i != self.player_local.current_weapon_idx else (0,0,0))
                self.screen.blit(txt, (rect.x + 10, rect.y + 15))
                self.screen.blit(self.ui_font.render(str(i+1), True, (150,150,150)), (rect.x+2, rect.y+2))
        
        # Kill Feed
        self.kill_feed.update_and_draw(self.screen)
        
        # Stats in alto
        if my_stats:
            stats_surf = self.font.render(f"HP: {int(my_stats['hp'])} | ALIVE: {len([p for p in players.values() if not p['is_dead']])}", True, (255,255,255))
            self.screen.blit(stats_surf, (10, 10))

        # Schermata Vittoria / Attesa
        if winner is not None:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.set_alpha(150); overlay.fill((0,0,50))
            self.screen.blit(overlay, (0,0))
            
            txt = self.font_win.render("#1 VICTORY ROYALE", True, GOLD)
            self.screen.blit(txt, (SCREEN_WIDTH//2 - txt.get_width()//2, SCREEN_HEIGHT//2 - 50))
            sub = self.font.render(f"Winner: Player {winner}", True, (255,255,255))
            self.screen.blit(sub, (SCREEN_WIDTH//2 - sub.get_width()//2, SCREEN_HEIGHT//2 + 50))
        
        elif len(players) < 2 and winner is None:
            txt = self.font.render("Waiting for players...", True, (200,200,200))
            self.screen.blit(txt, (SCREEN_WIDTH//2 - 60, 20))

        # Mirino
        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(self.screen, (255, 255, 255), (mx, my), 10, 2)

if __name__ == "__main__":
    Game().run()