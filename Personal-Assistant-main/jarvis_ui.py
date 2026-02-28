import pygame
import pyaudio
import struct
import threading
import os
import sys
import platform
import cv2
from PIL import Image, ImageSequence
import datetime
import subprocess
import time

script_dir = os.path.dirname(__file__)

# Global variables
grab_active = False

# Color definitions
CYAN = (0, 255, 255)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
LIGHT_CYAN = (0, 200, 200)
DARK_BLUE = (10, 20, 40)
HIGHLIGHT_ALPHA = 80

# Initialize pygame
pygame.init()

# Cross-platform font handling
def get_font_path():
    system = platform.system()
    if system == "Darwin":  # macOS
        return "Orbitron-VariableFont_wght.ttf"
    else:  # Windows/Linux fallback
        return None

font_path = get_font_path()
if font_path and os.path.exists(font_path):
    clock_font = pygame.font.Font(font_path, 72)
    clock_shadow_font = pygame.font.Font(font_path, 72)
    description_font = pygame.font.Font(font_path, 16)
    todo_font = pygame.font.Font(font_path, 28)
else:
    # Fallback fonts
    clock_font = pygame.font.SysFont("Arial", 72, bold=True)
    clock_shadow_font = pygame.font.SysFont("Arial", 72, bold=True)
    description_font = pygame.font.SysFont("Arial", 16)
    todo_font = pygame.font.SysFont("Arial", 28)
track_font = pygame.font.SysFont("Arial", 26)

# Cross-platform todo file
todo_file_path = ".todo.txt"
pico_description_lines = [
    
    "MateoTechLab File: Project Pico",
    "Personality is stable, but can be customized",
    "Uses an ESP32 Wrover module",
    "Open-source and community-driven",
    "Supports various sensors and modules",
    "Ideal for personal projects and educational purposes",
    
]

# Screen setup
screen_width, screen_height = 1920, 1080
screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
pygame.display.set_caption('J.A.R.V.I.S')

def load_image_safe(path, default_size=(200, 200)):
    """Safely load images with fallback"""
    if os.path.exists(path):
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.scale(img, default_size)
        except:
            pass
    surf = pygame.Surface(default_size)
    surf.fill(CYAN)
    return surf

# Load GIFs safely
def load_gif_safe(gif_path, fallback_frames=10):
    try:
        gif = Image.open(gif_path)
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(gif)]
        return [pygame.image.frombuffer(frame.tobytes(), frame.size, "RGBA") for frame in frames]
    except:
        frames = []
        size = (200, 200)
        for i in range(fallback_frames):
            surf = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.circle(surf, CYAN, (size[0]//2, size[1]//2), 50 + i*2)
            frames.append(surf)
        return frames

gif_path = os.path.join(script_dir, 'im.gif')
pico_gif_path = os.path.join(script_dir, 'picogram.gif')
premium_path = os.path.join(script_dir, 'jarvis_premium.png')

frame_surfaces = load_gif_safe(gif_path)
pico_surfaces = load_gif_safe(pico_gif_path)

# Load premium background image safely
def load_premium():
    if os.path.exists(premium_path):
        try:
            img = pygame.image.load(premium_path).convert_alpha()
            return img
        except:
            return None
    return None

premium_bg = load_premium()

# PyAudio setup with error handling
p = None
stream = None
def init_audio():
    global p, stream
    try:
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, 
                       input=True, frames_per_buffer=512)
        return True
    except:
        print("Audio input not available, running without microphone")
        return False

audio_available = init_audio()

def get_volume(data):
    if not data:
        return 0
    count = len(data) // 2
    format_str = f"%dh" % count
    shorts = struct.unpack(format_str, data)
    sum_squares = sum(s**2 for s in shorts)
    return (sum_squares / count)**0.5

def load_todo_tasks():
    if os.path.exists(todo_file_path):
        try:
            with open(todo_file_path, "r", encoding='utf-8') as f:
                return [line.strip() for line in f.readlines() if line.strip()]
        except:
            pass
    return []

track = ""
track_lock = threading.Lock()

def fetch_track():
    global track
    try:
        system = platform.system()
        if system == "Darwin":
            running = subprocess.check_output(
                'ps -ef | grep "MacOS/Spotify" | grep -v "grep" | wc -l',
                shell=True, text=True
            ).strip()
            if running == "0":
                new_track = ""
            else:
                new_track = subprocess.check_output(
                    """osascript -e 'tell application "Spotify"
                    set t to current track
                    return artist of t & " - " & name of t
                    end tell'""",
                    shell=True, text=True
                ).strip()
        else:
            new_track = ""
    except:
        new_track = ""
    
    with track_lock:
        track = new_track

def toggle_fullscreen(screen):
    global screen_width, screen_height
    info = pygame.display.Info()
    screen_width, screen_height = info.current_w, info.current_h
    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    return screen

def main():
    global screen, grab_active
    running = True
    fullscreen = False
    frame_idx = 0
    pico_idx = 0
    gif_scale = 1.0
    clock = pygame.time.Clock()
    track_update_ms = 3000
    last_track_ms = 0
    pico_x = None
    pico_y = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = toggle_fullscreen(screen)
                    else:
                        screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
                elif event.key == pygame.K_ESCAPE:
                    running = False

        # Audio volume visualization
        try:
            if audio_available and stream:
                audio_data = stream.read(2048, exception_on_overflow=False)
                volume = get_volume(audio_data)
                scale_factor = 1 + min(volume / 1000, 1)
                gif_scale = 0.9 * gif_scale + 0.1 * scale_factor
            else:
                gif_scale *= 0.99
        except:
            pass

        # Update track info
        now_ms = pygame.time.get_ticks()
        if now_ms - last_track_ms >= track_update_ms:
            threading.Thread(target=fetch_track, daemon=True).start()
            last_track_ms = now_ms

        # **PURE BLACK BACKGROUND** - Removed gradient overlay
        screen.fill(BLACK)

        # **PREMIUM BACKGROUND RENDERING**
        if premium_bg:
            # Render the premium HUD image in the center
            # It pulses with the voice volume
            bg_target_width = int(550 * gif_scale)
            bg_target_height = int(550 * gif_scale)
            scaled_bg = pygame.transform.scale(premium_bg, (bg_target_width, bg_target_height)).convert_alpha()
            
            bg_rect = scaled_bg.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 50))
            screen.blit(scaled_bg, bg_rect)

        # Render JARVIS Core GIF (The pulsing "eye" in the middle)
        scaled_width = int(180 * gif_scale)
        scaled_height = int(180 * gif_scale)

        jarvis_frame = frame_surfaces[frame_idx]
        jarvis_scaled = pygame.transform.scale(jarvis_frame, (scaled_width, scaled_height)).convert_alpha()
        
        # Cyan tint effect
        jarvis_tint = pygame.Surface((scaled_width, scaled_height), pygame.SRCALPHA)
        jarvis_tint.fill(CYAN + (100,))
        jarvis_scaled.blit(jarvis_tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Position JARVIS eye in the center of the holographic HUD
        jarvis_rect = jarvis_scaled.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 50))
        screen.blit(jarvis_scaled, jarvis_rect)

        # PICO rendering (Subtle assistant in top right)
        pico_frame = pico_surfaces[pico_idx]
        pico_target_width = 150
        pico_target_height = int(pico_frame.get_height() * (pico_target_width / pico_frame.get_width()))
        pico_scaled = pygame.transform.scale(pico_frame, (pico_target_width, pico_target_height)).convert_alpha()
        
        pico_x = screen.get_width() - pico_target_width - 30
        pico_y = 30
        screen.blit(pico_scaled, (int(pico_x), int(pico_y)))

        # PICO description side panel (Right side)
        for i, line in enumerate(pico_description_lines):
            line_surface = description_font.render(line, True, LIGHT_CYAN)
            line_x = screen.get_width() - 250
            line_y = pico_y + pico_target_height + 20 + i * 20
            screen.blit(line_surface, (line_x, line_y))

        # MODERN CLOCK DISPLAY (Floating at the top)
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M:%S")
        date_str = now.strftime("%A, %B %d, %Y")
        
        time_shadow = clock_shadow_font.render(current_time, True, BLACK)
        time_shadow_rect = time_shadow.get_rect(center=(screen.get_width() // 2 + 3, 73))
        screen.blit(time_shadow, time_shadow_rect)
        
        time_surface = clock_font.render(current_time, True, CYAN)
        time_rect = time_surface.get_rect(center=(screen.get_width() // 2, 70))
        screen.blit(time_surface, time_rect)
        
        date_surface = pygame.font.SysFont("Arial", 22, bold=True).render(date_str, True, WHITE)
        date_rect = date_surface.get_rect(center=(screen.get_width() // 2, 115))
        screen.blit(date_surface, date_rect)

        # Welcome message
        welcome_surface = pygame.font.SysFont("Arial", 18, italic=True).render("System online • Welcome, Vaibhav Sir", True, LIGHT_CYAN)
        welcome_rect = welcome_surface.get_rect(center=(screen.get_width() // 2, 145))
        screen.blit(welcome_surface, welcome_rect)

        # Current track (Bottom Left)
        with track_lock:
            current_track = track
        if current_track:
            track_surface = track_font.render(f"♫ {current_track}", True, LIGHT_CYAN)
            track_pos = (30, screen.get_height() - 50)
            screen.blit(track_surface, track_pos)

        # To-Do list (Left side)
        todo_tasks = load_todo_tasks()
        todo_x, todo_y = 30, 200
        todo_title = track_font.render("DAILY TASKS:", True, WHITE)
        screen.blit(todo_title, (todo_x, todo_y - 30))
        for i, task in enumerate(todo_tasks[:10]):
            todo_surface = todo_font.render(f"• {task}", True, LIGHT_CYAN)
            screen.blit(todo_surface, (todo_x, todo_y + i * 30))

        pygame.display.flip()
        frame_idx = (frame_idx + 1) % len(frame_surfaces)
        pico_idx = (pico_idx + 1) % len(pico_surfaces)
        clock.tick(30)

    # Cleanup
    if stream:
        stream.stop_stream()
        stream.close()
    if p:
        p.terminate()
    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    main()
