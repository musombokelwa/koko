#!/usr/bin/env python3
"""Actions contrôlées pour Kokoro : web, fichiers (lecture), musique.

Interdit : supprimer, modifier, créer des fichiers, exécuter des commandes shell.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

log = logging.getLogger("kokoro_actions")

_TAG_RE = re.compile(
    r"\[(OPEN|SEARCH|OPEN_FILE|LIST|READ|MUSIC):\s*(.*?)\]",
    re.IGNORECASE | re.DOTALL,
)

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".json",
    ".csv",
    ".log",
    ".cfg",
    ".ini",
    ".toml",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".sh",
    ".bash",
    ".env",
    ".rst",
    ".xml",
    ".sql",
    ".r",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".tex",
    ".org",
    ".adoc",
}

_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

_MAX_READ_CHARS = 4000
_MAX_LIST_ENTRIES = 40
_MAX_SEARCH_DEPTH = 6
_BINARY_EXT_BLOCK = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".rar",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mkv",
    ".avi",
    ".exe",
    ".so",
    ".dll",
    ".bin",
    ".pyc",
    ".o",
}


def allowed_roots() -> list[Path]:
    """Dossiers accessibles (lecture / ouverture)."""
    override = (os.environ.get("KOKORO_ALLOWED_PATHS") or "").strip()
    roots: list[Path] = []
    if override:
        for part in override.split(":"):
            part = part.strip()
            if not part:
                continue
            try:
                roots.append(Path(part).expanduser().resolve())
            except OSError:
                continue
    else:
        home = Path.home()
        candidates = [
            home,
            home / "Téléchargements",
            home / "Downloads",
            home / "Documents",
            home / "Bureau",
            home / "Desktop",
            Path(__file__).resolve().parent,
        ]
        for c in candidates:
            try:
                if c.is_dir():
                    roots.append(c.resolve())
            except OSError:
                continue

    seen: set[Path] = set()
    unique: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def _is_under_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in allowed_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _expand_user_path(raw: str) -> Path:
    text = raw.strip().strip('"').strip("'")
    aliases = {
        "téléchargements": "Téléchargements",
        "telechargements": "Téléchargements",
        "downloads": "Downloads",
        "documents": "Documents",
        "bureau": "Bureau",
        "desktop": "Desktop",
        "maison": "",
        "home": "",
        "dossier personnel": "",
    }
    lower = text.lower()
    if lower in aliases or lower in ("~", "home", "maison"):
        key = aliases.get(lower, "")
        return (Path.home() / key).resolve() if key else Path.home().resolve()
    return Path(text).expanduser()


def _find_in_roots(name: str) -> Path | None:
    needle = name.strip().strip('"').strip("'")
    if not needle:
        return None

    # Chemin absolu / relatif / ~ 
    as_path = _expand_user_path(needle)
    try:
        if as_path.exists() and _is_under_allowed(as_path):
            return as_path.resolve()
    except OSError:
        pass

    # "fichier X dans Documents" → extraire nom + dossier
    folder_hint: Path | None = None
    m = re.search(
        r"(.+?)\s+(?:dans|in)\s+(téléchargements|telechargements|downloads|"
        r"documents|bureau|desktop|maison|home)\s*$",
        needle,
        re.I,
    )
    search_name = needle
    if m:
        search_name = m.group(1).strip()
        folder_hint = _expand_user_path(m.group(2))

    name_lower = Path(search_name).name.lower()
    stem_lower = Path(search_name).stem.lower()
    roots = [folder_hint] if folder_hint and folder_hint.is_dir() else allowed_roots()

    exact: Path | None = None
    partial: Path | None = None

    for root in roots:
        if root is None:
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Limiter la profondeur et ignorer les dossiers cachés / lourds
                rel = Path(dirpath).relative_to(root)
                if len(rel.parts) > _MAX_SEARCH_DEPTH:
                    dirnames[:] = []
                    continue
                dirnames[:] = [
                    d
                    for d in dirnames
                    if not d.startswith(".")
                    and d.lower()
                    not in {
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "venv",
                        ".venv",
                        "dist",
                        "build",
                    }
                ]
                for fn in filenames:
                    if fn.startswith("."):
                        continue
                    fl = fn.lower()
                    p = Path(dirpath) / fn
                    if not _is_under_allowed(p):
                        continue
                    if fl == name_lower:
                        return p.resolve()
                    if exact is None and Path(fn).stem.lower() == stem_lower:
                        exact = p.resolve()
                    if (
                        partial is None
                        and len(stem_lower) >= 3
                        and stem_lower in fl
                    ):
                        partial = p.resolve()
        except OSError:
            continue

    return exact or partial


def _looks_like_text(path: Path) -> bool:
    suf = path.suffix.lower()
    if suf in _BINARY_EXT_BLOCK:
        return False
    if suf in _TEXT_EXTENSIONS or suf == "":
        return True
    # Essai : si ça se décode en texte sans trop de null bytes
    try:
        raw = path.read_bytes()[:2048]
    except OSError:
        return False
    if b"\x00" in raw:
        return False
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _open_path(path: Path) -> str:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return f"J'ai ouvert {path.name}."
    except OSError as e:
        log.warning("open failed: %s", e)
        return f"Impossible d'ouvrir {path.name}."


def _action_open(url: str) -> str:
    u = url.strip()
    if not u:
        return "Aucune adresse à ouvrir."
    if not re.match(r"^https?://", u, re.I):
        if "." in u and " " not in u:
            u = "https://" + u
        else:
            return _action_search(u)
    try:
        webbrowser.open(u)
        return "J'ai ouvert le site dans le navigateur."
    except OSError as e:
        log.warning("webbrowser.open failed: %s", e)
        return "Impossible d'ouvrir le site."


def _action_search(query: str) -> str:
    q = query.strip()
    if not q:
        return "Aucune recherche à lancer."
    url = f"https://www.google.com/search?q={quote_plus(q)}"
    try:
        webbrowser.open(url)
        return f"Voici les résultats pour {q}."
    except OSError as e:
        log.warning("search open failed: %s", e)
        return "Impossible d'ouvrir la recherche."


def _action_open_file(spec: str) -> str:
    path = _find_in_roots(spec)
    if path is None:
        return f"Je n'ai pas trouvé le fichier {spec.strip()}."
    if not path.is_file():
        return f"{path.name} n'est pas un fichier."
    return _open_path(path)


def _action_list(spec: str) -> str:
    raw = spec.strip()
    folder = _expand_user_path(raw) if raw else Path.home()
    if not folder.is_dir():
        found = _find_in_roots(raw)
        if found and found.is_dir():
            folder = found
        else:
            return f"Dossier introuvable : {raw or 'personnel'}."
    if not _is_under_allowed(folder):
        return "Ce dossier n'est pas accessible."
    try:
        entries = [
            p
            for p in folder.iterdir()
            if not p.name.startswith(".")
        ]
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        log.warning("list failed: %s", e)
        return "Impossible de lister ce dossier."
    if not entries:
        return f"Le dossier {folder.name} est vide."
    shown = entries[:_MAX_LIST_ENTRIES]
    names = []
    for p in shown:
        names.append(f"{p.name}/" if p.is_dir() else p.name)
    extra = len(entries) - len(shown)
    label = folder.name if folder != Path.home() else "votre dossier personnel"
    msg = f"Dans {label} : " + ", ".join(names)
    if extra > 0:
        msg += f", et {extra} autres éléments"
    return msg + "."


def _action_read(spec: str) -> str:
    path = _find_in_roots(spec)
    if path is None:
        return (
            f"Je n'ai pas trouvé le fichier {spec.strip()}. "
            "Donnez-moi le nom exact, ou le dossier, par exemple : "
            "lis notes.txt dans Documents."
        )
    if not path.is_file():
        return f"{path.name} n'est pas un fichier."
    if not _looks_like_text(path):
        return (
            f"Je ne peux pas lire {path.name} à voix haute "
            f"(format {path.suffix or 'binaire'}). "
            "Je peux l'ouvrir si vous voulez."
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("read failed: %s", e)
        return f"Impossible de lire {path.name}."
    # Nettoyage léger pour la lecture orale
    text = text.replace("\r\n", "\n").replace("\t", " ")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return f"Le fichier {path.name} est vide."
    if len(text) > _MAX_READ_CHARS:
        text = text[:_MAX_READ_CHARS].rsplit(" ", 1)[0] + ". … je m'arrête ici pour l'instant."
    return f"Je vous lis {path.name}. {text}"


def _action_music(spec: str) -> str:
    raw = spec.strip()
    if not raw:
        return "Aucune musique à lancer."
    if re.match(r"^https?://", raw, re.I):
        try:
            webbrowser.open(raw)
            return "J'ai lancé la musique dans le navigateur."
        except OSError:
            return "Impossible d'ouvrir la musique."

    path = _find_in_roots(raw)
    if path is None:
        return f"Fichier audio introuvable : {raw}."
    if path.suffix.lower() not in _AUDIO_EXTENSIONS:
        return _open_path(path)
    try:
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Je lance {path.name}."
    except OSError:
        return _open_path(path)


_HANDLERS = {
    "OPEN": _action_open,
    "SEARCH": _action_search,
    "OPEN_FILE": _action_open_file,
    "LIST": _action_list,
    "READ": _action_read,
    "MUSIC": _action_music,
}


def process_actions(reply: str) -> tuple[str, list[str]]:
    """Extrait et exécute les balises d'action. Retourne (texte propre, résultats)."""
    results: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        kind = match.group(1).upper()
        arg = (match.group(2) or "").strip()
        handler = _HANDLERS.get(kind)
        if handler is None:
            return ""
        try:
            results.append(handler(arg))
        except Exception as e:
            log.exception("Action %s failed", kind)
            results.append(f"Échec de l'action {kind} : {e}")
        return ""

    clean = _TAG_RE.sub(_replace, reply)
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = re.sub(r"  +", " ", clean).strip()
    return clean, results
