#!/usr/bin/env python3
"""Interface de lancement de Kokoro.

Lancer avec :
    python run.py

L'interface reste volontairement basée sur Tkinter : elle ne demande aucune
 dépendance supplémentaire et peut démarrer/arrêter le moteur vocal proprement.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
BG = "#07111f"
PANEL = "#0c1b2d"
TEXT = "#e8f4ff"
MUTED = "#87a6c2"
CYAN = "#65e4ff"
BLUE = "#4d83ff"
GREEN = "#6df2b0"
RED = "#ff8297"

# Repères d'interface : score composite indicatif (économie + maturité numérique).
# Il sert à visualiser les zones d'influence, pas à publier un classement officiel.
# Les repères s'inspirent des données PIB 2024 de la Banque mondiale et du
# World Digital Competitiveness Ranking 2025 de l'IMD.
COUNTRY_POWER = [
    ("États-Unis", 38.9, 100, 37.0, -77.0),
    ("Chine", 35.4, 92, 104.0, 35.0),
    ("Japon", 24.0, 66, 138.0, 36.0),
    ("Allemagne", 23.0, 65, 10.0, 51.0),
    ("Inde", 21.5, 61, 79.0, 22.0),
    ("Royaume-Uni", 20.0, 63, -2.0, 54.0),
    ("France", 18.0, 60, 2.0, 46.0),
    ("Corée du Sud", 17.0, 70, 127.5, 36.0),
    ("Canada", 16.0, 72, -106.0, 56.0),
    ("Suisse", 15.0, 78, 8.0, 47.0),
    ("Singapour", 14.0, 76, 104.0, 1.3),
    ("Brésil", 11.0, 40, -51.0, -10.0),
    ("Afrique du Sud", 7.0, 30, 24.0, -30.0),
    ("RDC", 3.0, 18, 23.7, -4.0),
]


class KokoroLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Kokoro · assistant vocal")
        self.geometry("980x680")
        self.minsize(760, 560)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.attributes("-alpha", 0.97)
        except tk.TclError:
            pass

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.angle = 0.0
        self.last_frame = time.monotonic()
        self.reduce_motion = False
        self.country_focus = None
        self.voice_speed = tk.DoubleVar(value=0.85)
        self.voice_volume = tk.DoubleVar(value=0.90)
        self.voice_pauses = tk.IntVar(value=450)
        self.voice_expressiveness = tk.DoubleVar(value=0.72)
        self.natural_mode = tk.BooleanVar(value=True)

        self._build_ui()
        self._animate()
        self.after(120, self._poll_output)
        # Le launcher est une présence permanente : la conversation commence
        # automatiquement dès que la fenêtre est ouverte.
        self.after(250, self.start_process)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=46, pady=(30, 0))
        header.grid_columnconfigure(0, weight=1)

        brand = tk.Label(
            header,
            text="KOKORO",
            bg=BG,
            fg=TEXT,
            font=("Helvetica", 22, "bold"),
        )
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="ASSISTANT VOCAL LOCAL  ·  ESPACE PRIVÉ",
            bg=BG,
            fg=MUTED,
            font=("Helvetica", 9, "bold"),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.status_dot = tk.Label(header, text="●", bg=BG, fg=MUTED, font=("Helvetica", 12))
        self.status_dot.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self.status = tk.Label(
            header,
            text="INITIALISATION",
            bg=BG,
            fg=MUTED,
            font=("Helvetica", 9, "bold"),
        )
        self.status.grid(row=0, column=2, rowspan=2, padx=(5, 0))

        body = tk.Frame(self, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=38, pady=22)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        globe_frame = tk.Frame(body, bg=BG)
        globe_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        globe_frame.grid_rowconfigure(0, weight=1)
        globe_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(globe_frame, bg=BG, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        panel = tk.Frame(
            body,
            bg=PANEL,
            highlightbackground="#1b3650",
            highlightthickness=1,
        )
        panel.grid(row=0, column=1, sticky="nsew", pady=32)
        panel.grid_columnconfigure(0, weight=1)

        tk.Label(panel, text="CENTRE DE CONTRÔLE", bg=PANEL, fg=CYAN,
                 font=("Helvetica", 9, "bold")).grid(row=0, column=0, sticky="w", padx=27, pady=(28, 7))
        tk.Label(panel, text="Votre espace vocal,\nla conversation commence.", bg=PANEL, fg=TEXT,
                 justify="left", font=("Helvetica", 22, "bold")).grid(row=1, column=0, sticky="w", padx=27)
        tk.Label(panel, text="Parlez naturellement. Koko écoute, comprend,\nrecherche et répond à voix haute.", bg=PANEL, fg=MUTED,
                 justify="left", font=("Helvetica", 10)).grid(row=2, column=0, sticky="w", padx=27, pady=(14, 25))

        tk.Label(panel, text="ÉTAT DU SYSTÈME", bg=PANEL, fg=MUTED,
                 font=("Helvetica", 8, "bold")).grid(row=4, column=0, sticky="w", padx=27, pady=(34, 7))
        self.detail = tk.Label(panel, text="Moteur vocal arrêté\nMicrophone en attente\nVision : prête, permission requise",
                               bg=PANEL, fg=TEXT, justify="left", anchor="w",
                               font=("Helvetica", 10), pady=5)
        self.detail.grid(row=5, column=0, sticky="ew", padx=27)
        self.power_label = tk.Label(
            panel,
            text="SIGNAL ÉCONOMIQUE / NUMÉRIQUE\nRotation active · indice indicatif",
            bg=PANEL,
            fg="#78cde4",
            justify="left",
            anchor="w",
            font=("Helvetica", 9),
        )
        self.power_label.grid(row=6, column=0, sticky="ew", padx=27, pady=(28, 0))

        tk.Label(panel, text="VOIX & CONVERSATION", bg=PANEL, fg=MUTED,
                 font=("Helvetica", 8, "bold")).grid(row=7, column=0, sticky="w", padx=27, pady=(18, 7))
        voice_panel = tk.Frame(panel, bg="#071525")
        voice_panel.grid(row=8, column=0, sticky="ew", padx=27, pady=(0, 12))
        voice_panel.grid_columnconfigure(1, weight=1)

        def add_voice_scale(row: int, label: str, variable: tk.Variable,
                            start: float, end: float, resolution: float) -> None:
            tk.Label(voice_panel, text=label, bg="#071525", fg=MUTED,
                     font=("Helvetica", 8)).grid(row=row, column=0, sticky="w", padx=8)
            tk.Scale(voice_panel, variable=variable, from_=start, to=end,
                     resolution=resolution, orient="horizontal", showvalue=True,
                     bg="#071525", fg=TEXT, troughcolor="#1b3650",
                     highlightthickness=0, bd=0, length=155,
                     font=("Helvetica", 8)).grid(row=row, column=1, sticky="ew", padx=4)

        add_voice_scale(0, "Vitesse", self.voice_speed, 0.85, 1.10, 0.01)
        add_voice_scale(1, "Volume", self.voice_volume, 0.50, 1.00, 0.01)
        add_voice_scale(2, "Expressivité", self.voice_expressiveness, 0.00, 1.00, 0.01)
        add_voice_scale(3, "Pause", self.voice_pauses, 80, 500, 10)
        tk.Checkbutton(voice_panel, text="Mode conversation naturelle", variable=self.natural_mode,
                       bg="#071525", fg=TEXT, activebackground="#071525", activeforeground=TEXT,
                       selectcolor="#1b3650", highlightthickness=0, anchor="w",
                       font=("Helvetica", 8)).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=(2, 0))
        tk.Button(voice_panel, text="Appliquer et relancer", command=self.apply_voice_settings,
                  bg="#123954", fg=TEXT, activebackground="#245b7a", activeforeground=TEXT,
                  relief="flat", bd=0, cursor="hand2", font=("Helvetica", 8),
                  padx=8, pady=4).grid(row=5, column=0, columnspan=2, sticky="e", padx=5, pady=(5, 5))

        tk.Label(panel, text="FIL DE CONVERSATION", bg=PANEL, fg=MUTED,
                 font=("Helvetica", 8, "bold")).grid(row=9, column=0, sticky="w", padx=27, pady=(6, 7))
        self.transcript = tk.Text(
            panel, height=9, wrap="word", state="disabled",
            bg="#071525", fg=TEXT, insertbackground=TEXT,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#1b3650", highlightcolor="#65e4ff",
            font=("Helvetica", 9), padx=10, pady=8,
        )
        self.transcript.grid(row=10, column=0, sticky="nsew", padx=27, pady=(0, 20))
        panel.grid_rowconfigure(10, weight=1)

        footer = tk.Frame(self, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=46, pady=(0, 25))
        footer.grid_columnconfigure(0, weight=1)
        tk.Label(footer, text="Koko parle et écoute automatiquement · Fermez la fenêtre pour arrêter",
                 bg=BG, fg=MUTED, font=("Helvetica", 9)).grid(row=0, column=0, sticky="w")
        tk.Button(footer, text="Mouvement réduit", command=self.toggle_motion,
                  bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
                  relief="flat", bd=0, cursor="hand2", font=("Helvetica", 9)).grid(row=0, column=1, sticky="e")

    def _draw_globe(self) -> None:
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 320)
        h = max(self.canvas.winfo_height(), 320)
        cx, cy = w * 0.5, h * 0.5
        radius = min(w, h) * 0.34

        # Halo doux et lignes de latitude/longitude : transparence visuelle sans image externe.
        for scale, color in ((1.20, "#0a2033"), (1.10, "#0d2b42"), (1.02, "#123954")):
            r = radius * scale
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="")
        self.canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius,
                                fill="#0a2235", outline="#67dfff", width=2)
        self.canvas.create_oval(cx-radius+6, cy-radius+6, cx+radius-6, cy+radius-6,
                                outline="#245b7a", width=1)

        # Projection d'un globe filaire : les ellipses tournent en fonction de l'angle.
        import math
        for i in range(-3, 4):
            y = cy + radius * i / 4
            half = radius * math.sqrt(max(0.0, 1 - (i / 4) ** 2))
            self.canvas.create_arc(cx-half, y-radius*0.17, cx+half, y+radius*0.17,
                                   start=0, extent=180, style="arc", outline="#3f9abb", width=1)
            self.canvas.create_arc(cx-half, y-radius*0.17, cx+half, y+radius*0.17,
                                   start=180, extent=180, style="arc", outline="#194c6b", width=1)
        for i in range(8):
            longitude = (i / 8) * math.pi + self.angle
            width = radius * abs(math.sin(longitude))
            self.canvas.create_oval(cx-width, cy-radius, cx+width, cy+radius,
                                    outline="#2b7898" if i % 2 else "#50b4d0", width=1)

        # Pays repérés sur la surface visible : longitude + rotation donnent
        # l'effet de globe vivant. Le score augmente la taille et la lumière.
        projected = []
        for name, gdp, score, lon, lat in COUNTRY_POWER:
            lon_rad, lat_rad = math.radians(lon) + self.angle, math.radians(lat)
            cos_lat = math.cos(lat_rad)
            z = cos_lat * math.cos(lon_rad)
            if z < -0.08:
                continue
            x = cx + radius * 0.94 * math.cos(lat_rad) * math.sin(lon_rad)
            y = cy - radius * 0.94 * math.sin(lat_rad)
            projected.append((z, name, gdp, score, x, y))
        projected.sort(reverse=True)
        if projected:
            _, name, gdp, score, _, _ = projected[0]
            self.country_focus = name
            self.power_label.configure(
                text=f"PAYS POINTÉ · {name.upper()}\nIndice {score}/100 · PIB {gdp:.1f} T$ · rotation active"
            )
        for index, (z, name, _gdp, score, x, y) in enumerate(projected):
            size = 3 + score / 24
            color = "#b9fbff" if index == 0 else ("#72e9ff" if z > 0.5 else "#3d9ab8")
            self.canvas.create_oval(x-size, y-size, x+size, y+size, fill=color, outline="")
            # Ne montrer que les repères les plus proches pour garder une lecture nette.
            if index < 5 and z > 0.22:
                self.canvas.create_text(x + 9, y - 8, text=name, anchor="w",
                                        fill="#d8f8ff" if index == 0 else "#80b9ce",
                                        font=("Helvetica", 9, "bold" if index == 0 else "normal"))

        # Points de présence qui donnent une sensation de réseau vivant.
        for i in range(10):
            a = self.angle * 1.7 + i * 0.92
            px = cx + math.cos(a) * radius * (0.45 + (i % 3) * 0.13)
            py = cy + math.sin(a * 1.4) * radius * 0.68
            size = 2 + (i % 3)
            self.canvas.create_oval(px-size, py-size, px+size, py+size, fill=CYAN, outline="")
        self.canvas.create_text(cx, cy + radius + 42, text="PRÉSENCE LOCALE  /  KOKORO ONLINE",
                                fill="#6eabc2", font=("Helvetica", 9, "bold"))

    def _animate(self) -> None:
        if not self.reduce_motion:
            now = time.monotonic()
            self.angle = (self.angle + (now - self.last_frame) * 0.65) % (2 * 3.14159)
            self.last_frame = now
            self._draw_globe()
        self.after(50, self._animate)

    def toggle_motion(self) -> None:
        self.reduce_motion = not self.reduce_motion
        if self.reduce_motion:
            self._draw_globe()

    def start_process(self) -> None:
        if not (ROOT / "kokoro.py").is_file():
            messagebox.showerror("Kokoro", "Le fichier kokoro.py est introuvable.")
            return
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(ROOT / "kokoro.py")],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ, **self._voice_environment(), "PYTHONUNBUFFERED": "1"},
            )
        except OSError as exc:
            messagebox.showerror("Impossible de démarrer Kokoro", str(exc))
            return
        self.status.configure(text="EN ÉCOUTE", fg=GREEN)
        self.status_dot.configure(fg=GREEN)
        self.detail.configure(text="Démarrage vocal en cours\nKoko va vous accueillir\nVision : prête, permission requise")
        self._append_transcript("KOKO", "Je suis là. La communication commence.")
        threading.Thread(target=self._read_output, daemon=True).start()

    def _voice_environment(self) -> dict[str, str]:
        """Transmet les réglages choisis au moteur vocal au prochain lancement."""
        return {
            "VOICE_SPEED": f"{self.voice_speed.get():.2f}",
            "VOICE_VOLUME": f"{self.voice_volume.get():.2f}",
            "VOICE_PAUSE_SENTENCE_MS": str(self.voice_pauses.get()),
            "VOICE_EXPRESSIVENESS": f"{self.voice_expressiveness.get():.2f}",
            "VOICE_NATURAL_MODE": "1" if self.natural_mode.get() else "0",
        }

    def apply_voice_settings(self) -> None:
        """Recharge le moteur pour appliquer les réglages sans laisser un ancien processus actif."""
        self.stop_process()
        self.status.configure(text="RECHARGEMENT DE LA VOIX", fg=CYAN)
        self.after(150, self.start_process)

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.output_queue.put(line.rstrip())

    def _poll_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_output(line)
        if self.process and self.process.poll() is not None:
            self._set_stopped()
        self.after(120, self._poll_output)

    def _append_transcript(self, speaker: str, message: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{speaker}\n{message.strip()}\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _handle_output(self, line: str) -> None:
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not clean:
            return
        if "Parlez..." in clean:
            self.status.configure(text="À VOUS DE PARLER", fg=CYAN)
            return
        if "Vous:" in clean:
            self._append_transcript("VOUS", clean.split("Vous:", 1)[1])
            self.status.configure(text="KOKO RÉFLÉCHIT", fg=CYAN)
            return
        if "Kokoro:" in clean:
            self._append_transcript("KOKO", clean.split("Kokoro:", 1)[1])
            self.status.configure(text="KOKO VOUS ÉCOUTE", fg=GREEN)
            return
        if clean.startswith("→"):
            self._append_transcript("ACTION", clean[1:].strip())
            return
        if clean.startswith("[VOIX]"):
            self._append_transcript("SYSTÈME", clean)
            self.status.configure(text="VOIX À CONFIGURER", fg="#ffb86b")
            return
        if "clé Gemini" in clean or "Gemini" in clean or "réseau" in clean.lower():
            self._append_transcript("SYSTÈME", "Connexion Gemini indisponible. Vérifiez la clé et le réseau.")
            self.status.configure(text="GEMINI INDISPONIBLE", fg="#ffb86b")
            return

    def stop_process(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._set_stopped()

    def _set_stopped(self) -> None:
        self.status.configure(text="ARRÊTÉ", fg=MUTED)
        self.status_dot.configure(fg=MUTED)
        self.detail.configure(text="Moteur vocal arrêté\nMicrophone en attente\nVision : prête, permission requise")
        self.process = None

    def close(self) -> None:
        self.stop_process()
        self.destroy()


if __name__ == "__main__":
    KokoroLauncher().mainloop()
