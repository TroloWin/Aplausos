import dearpygui.dearpygui as dpg
import os
import sys
import json
import threading
import time
import webbrowser
import subprocess
import numpy as np
import sounddevice as sd
import pyttsx3
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================

CONFIG_FILE = os.path.expanduser("~/.Aplausos-config.json")
DEFAULT_CONFIG = {
    "youtube_url": "",
    "mensaje": "",
    "ia_seleccionada": "Claude",
    "vscode_path": "",
    "umbral_aplauso": 0.03,
    "auto_start": False,
    "auto_listen": True
}

IA_URLS = {
    "Claude": "https://claude.ai/",
    "DeepSeek": "https://chat.deepseek.com/",
}

# Variables globales
current_config = None
clap_times = []
triggered = False
lock = threading.Lock()
nivel_ruido_fondo = 0.01
audio_stream = None
modo_compacto = True
app_instance = None

# ============================================================
# FUNCIONES DE CONFIGURACIÓN
# ============================================================

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        except:
            pass
    return DEFAULT_CONFIG.copy()

def guardar_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        return True
    except:
        return False

def encontrar_vscode():
    rutas = [
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            return ruta
    try:
        result = subprocess.run(["where", "code"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except:
        pass
    return None

def get_startup_folder():
    return os.path.join(os.environ['APPDATA'], 
                        r'Microsoft\Windows\Start Menu\Programs\Startup')

def crear_acceso_directo(script_path):
    try:
        startup_folder = get_startup_folder()
        shortcut_path = os.path.join(startup_folder, "Aplausos.lnk")
        
        powershell_script = f'''
        $WScriptShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WScriptShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{sys.executable}"
        $Shortcut.Arguments = '"{script_path}"'
        $Shortcut.WorkingDirectory = "{os.path.dirname(script_path)}"
        $Shortcut.Save()
        '''
        
        subprocess.run(["powershell", "-Command", powershell_script], capture_output=True)
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def eliminar_acceso_directo():
    startup_folder = get_startup_folder()
    shortcut_path = os.path.join(startup_folder, "Aplausos.lnk")
    if os.path.exists(shortcut_path):
        os.remove(shortcut_path)
        return True
    return False

def is_auto_start_enabled():
    startup_folder = get_startup_folder()
    shortcut_path = os.path.join(startup_folder, "Aplausos.lnk")
    return os.path.exists(shortcut_path)

# ============================================================
# DETECCIÓN DE APLAUSOS
# ============================================================

def calibrar_ruido_fondo(segundos=2):
    global nivel_ruido_fondo
    muestras = []
    def callback(indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(indata ** 2)))
        muestras.append(rms)
    try:
        with sd.InputStream(samplerate=44100, blocksize=int(44100 * 0.1),
                           channels=1, dtype="float32", callback=callback):
            time.sleep(segundos)
        if muestras:
            nivel_ruido_fondo = np.percentile(muestras, 90)
            return nivel_ruido_fondo
    except:
        pass
    return 0.01

def audio_callback(indata, frames, time_info, status):
    global triggered, clap_times, current_config
    if triggered or current_config is None:
        return
    rms = float(np.sqrt(np.mean(indata ** 2)))
    peak = float(np.max(np.abs(indata)))
    now = time.time()
    umbral = current_config.get("umbral_aplauso", 0.03)
    umbral_adaptativo = max(umbral, nivel_ruido_fondo * 3)
    es_aplauso = (rms > umbral_adaptativo and peak > rms * 1.3 and rms < 0.5)
    if es_aplauso:
        with lock:
            if clap_times and (now - clap_times[-1]) < 0.3:
                return
            clap_times.append(now)
            clap_times = [t for t in clap_times if now - t <= 1.5]
            if len(clap_times) >= 2:
                triggered = True
                clap_times = []
                threading.Thread(target=secuencia_bienvenida, daemon=True).start()

def secuencia_bienvenida():
    global triggered, current_config
    try:
        hora = datetime.now().strftime("%H:%M:%S")
        if app_instance:
            app_instance.agregar_log(f"¡ACTIVADO! Doble aplauso detectado a las {hora}")
            app_instance.actualizar_ultima_activacion(hora)
        
        if current_config.get("mensaje"):
            hablar(current_config["mensaje"])
        
        if current_config.get("youtube_url"):
            webbrowser.open(current_config["youtube_url"])
        time.sleep(1.2)
        
        ia_url = IA_URLS.get(current_config["ia_seleccionada"], IA_URLS["Claude"])
        webbrowser.open(ia_url)
        time.sleep(1.5)
        
        vscode_path = current_config.get("vscode_path") or encontrar_vscode()
        if vscode_path and os.path.exists(vscode_path):
            subprocess.Popen([vscode_path])
        else:
            try:
                subprocess.Popen(["code"], shell=True)
            except:
                pass
        time.sleep(2)
    except Exception as e:
        print(f"Error en secuencia: {e}")
    finally:
        triggered = False

def hablar(texto):
    if not texto:
        return
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'spanish' in voice.name.lower() or 'español' in voice.name.lower():
                engine.setProperty('voice', voice.id)
                break
        engine.setProperty('rate', 150)
        engine.say(texto)
        engine.runAndWait()
    except:
        pass

# ============================================================
# INTERFAZ PRINCIPAL
# ============================================================

class App:
    def __init__(self):
        global app_instance, current_config
        app_instance = self
        
        self.config = cargar_config()
        if not self.config.get("vscode_path"):
            self.config["vscode_path"] = encontrar_vscode()
        
        current_config = self.config
        self.is_listening = False
        self.listener_thread = None
        self.script_path = os.path.abspath(sys.argv[0])
        self.audio_stream = None
        
        self.setup_gui()
    
    def setup_gui(self):
        dpg.create_context()
        
        # Viewport
        dpg.create_viewport(
            title="APLAUSOS",
            width=300,
            height=240,
            resizable=False,
            x_pos=200,
            y_pos=100,
            decorated=True
        )
        
        # Tema oscuro con dorado
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (15, 15, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg, (200, 150, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, (220, 170, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (200, 150, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (220, 170, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 45, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255, 255))
        
        dpg.bind_theme(theme)
        
        # Ventana principal
        self.main_window = dpg.generate_uuid()
        with dpg.window(tag=self.main_window, label="", width=-1, height=-1, no_close=True, no_collapse=True, no_title_bar=True, no_move=True):
            self.crear_modo_compacto()
        
        dpg.setup_dearpygui()
        dpg.show_viewport()
        
        # Iniciar escucha automática
        if self.config.get("auto_listen", True):
            threading.Timer(2, lambda: self.iniciar_escucha(None)).start()
        
        dpg.start_dearpygui()
        dpg.destroy_context()
    
    def recrear_ventana(self):
        """Recrea la ventana principal con el modo actual"""
        if dpg.does_item_exist(self.main_window):
            dpg.delete_item(self.main_window)
        
        self.main_window = dpg.generate_uuid()
        with dpg.window(tag=self.main_window, label="", width=-1, height=-1, no_close=True, no_collapse=True, no_title_bar=True, no_move=True):
            if modo_compacto:
                self.crear_modo_compacto()
            else:
                self.crear_modo_completo()
    
    def crear_modo_compacto(self):
        """Crea la interfaz compacta"""
        dpg.add_text("🎤 APLAUSOS", color=(200, 150, 0, 255), parent=self.main_window)
        dpg.add_spacer(height=10, parent=self.main_window)
        
        dpg.add_text("Detenido", tag="status_text", color=(150, 150, 150, 255), parent=self.main_window)
        dpg.add_spacer(height=15, parent=self.main_window)
        
        with dpg.group(horizontal=True, parent=self.main_window):
            dpg.add_button(label="INICIAR", callback=self.iniciar_escucha, width=130, height=35)
            dpg.add_button(label="DETENER", callback=self.detener_escucha, width=130, height=35)
        
        dpg.add_spacer(height=10, parent=self.main_window)
        
        with dpg.group(horizontal=True, parent=self.main_window):
            dpg.add_button(label="AJUSTES", callback=self.cambiar_a_completo, width=130, height=35)
            dpg.add_button(label="SALIR", callback=self.salir, width=130, height=35)
        
        dpg.add_spacer(height=15, parent=self.main_window)

    
    def crear_modo_completo(self):
        """Crea la interfaz completa - IGUAL A LA ORIGINAL"""
        # Header
        dpg.add_text("APLAUSOS", color=(200, 150, 0, 255), parent=self.main_window)
        dpg.add_text("Sistema de Activación por Aplausos - Edición Premium", color=(180, 180, 180, 255), parent=self.main_window)
        dpg.add_spacer(height=20, parent=self.main_window)
        
        # Panel de estado
        with dpg.child_window(height=80, border=True, parent=self.main_window):
            with dpg.group(horizontal=True):
                dpg.add_text("ESTADO:", color=(200, 150, 0, 255))
                dpg.add_text("Iniciando...", tag="estado_texto", color=(200, 200, 200, 255))
            with dpg.group(horizontal=True):
                dpg.add_text("Última activación:", color=(200, 150, 0, 255))
                dpg.add_text("---", tag="ultima_activacion", color=(200, 200, 200, 255))
        
        dpg.add_spacer(height=15, parent=self.main_window)
        
        # Configuración 2 columnas
        with dpg.group(horizontal=True, parent=self.main_window):
            # Columna izquierda
            with dpg.child_window(width=420, height=350, border=True):
                dpg.add_text("CONFIGURACIÓN PRINCIPAL", color=(200, 150, 0, 255))
                dpg.add_separator()
                dpg.add_spacer(height=5)
                
                dpg.add_text("YouTube URL")
                dpg.add_input_text(tag="youtube_url", default_value=self.config["youtube_url"], width=380)
                dpg.add_spacer(height=10)
                
                dpg.add_text("Mensaje")
                dpg.add_input_text(tag="mensaje", default_value=self.config["mensaje"], width=380, height=50, multiline=True)
                dpg.add_spacer(height=10)
                
                dpg.add_text("Asistente IA")
                dpg.add_combo(tag="ia_seleccionada", items=list(IA_URLS.keys()), default_value=self.config["ia_seleccionada"], width=200)
                dpg.add_spacer(height=10)
                
                dpg.add_text("Visual Studio Code")
                with dpg.group(horizontal=True):
                    dpg.add_input_text(tag="vscode_path", default_value=self.config["vscode_path"] or "", width=300)
                    dpg.add_button(label="🔍", callback=self.buscar_vscode, width=40)
            
            # Columna derecha
            with dpg.child_window(width=420, height=350, border=True):
                dpg.add_text("AJUSTES AVANZADOS", color=(200, 150, 0, 255))
                dpg.add_separator()
                dpg.add_spacer(height=5)
                
                dpg.add_text("Sensibilidad de detección")
                dpg.add_slider_float(tag="umbral", default_value=self.config["umbral_aplauso"], min_value=0.01, max_value=0.15, width=380)
                dpg.add_text(f"Valor: {self.config['umbral_aplauso']:.3f}", tag="umbral_label")
                dpg.add_text("Menor valor = más sensible | Mayor = menos sensible", color=(150, 150, 150, 255))
                dpg.add_spacer(height=15)
                
                dpg.add_text("Inicio con Windows", color=(200, 150, 0, 255))
                dpg.add_checkbox(tag="auto_start", label="Iniciar aplicación al encender el PC", default_value=is_auto_start_enabled(), callback=self.toggle_auto_start)
                dpg.add_spacer(height=10)
                
                dpg.add_text("Inicio automático de escucha", color=(200, 150, 0, 255))
                dpg.add_checkbox(tag="auto_listen", label="Activar escucha automáticamente al abrir la app", default_value=self.config.get("auto_listen", True), callback=self.toggle_auto_listen)
                dpg.add_spacer(height=15)
                
                dpg.add_text("Nivel de ruido de fondo:", color=(200, 150, 0, 255))
                dpg.add_text("---", tag="ruido_fondo_label")
        
        dpg.add_spacer(height=15, parent=self.main_window)
        
        # Botones
        with dpg.group(horizontal=True, parent=self.main_window):
            dpg.add_button(label="GUARDAR", callback=self.guardar_config, width=140, height=40)
            dpg.add_button(label="INICIAR", callback=self.iniciar_escucha, width=140, height=40)
            dpg.add_button(label="DETENER", callback=self.detener_escucha, width=140, height=40)
            dpg.add_button(label="CALIBRAR", callback=self.calibrar_solo, width=140, height=40)
            dpg.add_button(label="COMPACTO", callback=self.cambiar_a_compacto, width=140, height=40)
            dpg.add_button(label="SALIR", callback=self.salir, width=140, height=40)
        
        dpg.add_spacer(height=15, parent=self.main_window)
        
        # Registro
        with dpg.collapsing_header(label="REGISTRO DE ACTIVIDAD", default_open=True, parent=self.main_window):
            dpg.add_text("Bienvenido al sistema", tag="log_text")
        
        dpg.add_spacer(height=10, parent=self.main_window)
        
        # Footer
        dpg.add_separator(parent=self.main_window)
        with dpg.group(horizontal=True, parent=self.main_window):
            dpg.add_text("Sistema listo para usar", color=(200, 150, 0, 255))
            dpg.add_text("|", color=(100, 100, 100, 255))
            dpg.add_text("Da DOS aplausos para activar", color=(180, 180, 180, 255))
        
        # Callback del slider
        def actualizar_umbral():
            dpg.set_value("umbral_label", f"Valor: {dpg.get_value('umbral'):.3f}")
        dpg.set_item_callback("umbral", actualizar_umbral)
        
        # Actualizar estado
        if self.is_listening:
            dpg.set_value("estado_texto", "🎤 ¡Escuchando! Da DOS aplausos")
    
    def cambiar_a_compacto(self):
        global modo_compacto
        modo_compacto = True
        dpg.set_viewport_width(300)
        dpg.set_viewport_height(240)
        dpg.set_viewport_title("APLAUSOS")
        self.recrear_ventana()
        if self.is_listening:
            dpg.set_value("status_text", "Escuchando...")
            dpg.set_value("compact_hint", "Escuchando...")
        else:
            dpg.set_value("status_text", "Detenido")
            dpg.set_value("compact_hint", "Da DOS aplausos")
    
    def cambiar_a_completo(self):
        global modo_compacto
        modo_compacto = False
        dpg.set_viewport_width(900)
        dpg.set_viewport_height(700)
        dpg.set_viewport_title("APLAUSOS - Sistema de Activación")
        self.recrear_ventana()
    
    def salir(self):
        self.detener_escucha()
        dpg.stop_dearpygui()
        sys.exit(0)
    
    def actualizar_ultima_activacion(self, hora):
        if dpg.does_item_exist("ultima_activacion"):
            dpg.set_value("ultima_activacion", hora)
    
    def toggle_auto_listen(self):
        self.config["auto_listen"] = dpg.get_value("auto_listen")
        guardar_config(self.config)
    
    def calibrar_solo(self):
        self.agregar_log("Calibrando micrófono... (mantén silencio)")
        nivel = calibrar_ruido_fondo(2)
        if dpg.does_item_exist("ruido_fondo_label"):
            dpg.set_value("ruido_fondo_label", f"{nivel:.4f}")
        self.agregar_log(f"Ruido de fondo calibrado: {nivel:.4f}")
    
    def agregar_log(self, mensaje):
        hora = datetime.now().strftime("%H:%M:%S")
        if dpg.does_item_exist("log_text"):
            actual = dpg.get_value("log_text")
            dpg.set_value("log_text", f"[{hora}] {mensaje}\n{actual}")
        print(mensaje)
    
    def buscar_vscode(self):
        ruta = encontrar_vscode()
        if ruta:
            dpg.set_value("vscode_path", ruta)
            self.agregar_log("VS Code encontrado")
        else:
            self.agregar_log("VS Code no encontrado")
    
    def toggle_auto_start(self):
        if dpg.get_value("auto_start"):
            if crear_acceso_directo(self.script_path):
                self.agregar_log("Inicio automático con Windows activado")
            else:
                self.agregar_log("Error al activar inicio automático")
                dpg.set_value("auto_start", False)
        else:
            eliminar_acceso_directo()
            self.agregar_log("Inicio automático con Windows desactivado")
    
    def guardar_config(self):
        if dpg.does_item_exist("youtube_url"):
            self.config["youtube_url"] = dpg.get_value("youtube_url")
            self.config["mensaje"] = dpg.get_value("mensaje")
            self.config["ia_seleccionada"] = dpg.get_value("ia_seleccionada")
            self.config["vscode_path"] = dpg.get_value("vscode_path")
            self.config["umbral_aplauso"] = dpg.get_value("umbral")
            self.config["auto_listen"] = dpg.get_value("auto_listen")
        
        if guardar_config(self.config):
            self.agregar_log("Configuración guardada")
        else:
            self.agregar_log("Error al guardar configuración")
    
    def iniciar_escucha(self, sender):
        global current_config
        
        if self.is_listening:
            self.agregar_log("Ya estoy escuchando")
            return
        
        current_config = self.config
        self.is_listening = True
        
        if modo_compacto:
            if dpg.does_item_exist("status_text"):
                dpg.set_value("status_text", "Escuchando...")
        else:
            if dpg.does_item_exist("estado_texto"):
                dpg.set_value("estado_texto", "Calibrando micrófono...")
        
        self.agregar_log("Calibrando micrófono...")
        
        def calibrar_y_escuchar():
            nivel = calibrar_ruido_fondo(2)
            if not modo_compacto and dpg.does_item_exist("ruido_fondo_label"):
                dpg.set_value("ruido_fondo_label", f"{nivel:.4f}")
            
            if modo_compacto:
                if dpg.does_item_exist("status_text"):
                    dpg.set_value("status_text", "¡Escuchando!")
                if dpg.does_item_exist("compact_hint"):
                    dpg.set_value("compact_hint", "¡Aplaude dos veces!")
            else:
                if dpg.does_item_exist("estado_texto"):
                    dpg.set_value("estado_texto", "¡Escuchando! Da DOS aplausos")
            
            self.agregar_log("¡Escuchando! Da DOS aplausos para activar")
            
            try:
                with sd.InputStream(samplerate=44100, blocksize=int(44100 * 0.1),
                                   channels=1, dtype="float32", callback=audio_callback) as stream:
                    self.audio_stream = stream
                    while self.is_listening:
                        time.sleep(0.1)
            except Exception as e:
                self.agregar_log(f"Error en stream: {e}")
                if modo_compacto:
                    if dpg.does_item_exist("status_text"):
                        dpg.set_value("status_text", "Error")
                    if dpg.does_item_exist("compact_hint"):
                        dpg.set_value("compact_hint", "Error en micrófono")
                else:
                    if dpg.does_item_exist("estado_texto"):
                        dpg.set_value("estado_texto", "Error en micrófono")
                self.is_listening = False
            finally:
                self.audio_stream = None
        
        self.listener_thread = threading.Thread(target=calibrar_y_escuchar, daemon=True)
        self.listener_thread.start()
    
    def detener_escucha(self):
        self.is_listening = False
        
        if modo_compacto:
            if dpg.does_item_exist("status_text"):
                dpg.set_value("status_text", "Detenido")
            if dpg.does_item_exist("compact_hint"):
                dpg.set_value("compact_hint", "Da DOS aplausos")
        else:
            if dpg.does_item_exist("estado_texto"):
                dpg.set_value("estado_texto", "Sistema detenido")
        
        self.agregar_log("Escucha detenida")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = App()