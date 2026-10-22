# Kokoro — assistant vocal local

Assistant de **discussion, recherche web et actions contrôlées** : lancement → conversation vocale directe avec Gemini et ElevenLabs.

## Ce qu'il peut faire

| Action | Exemple vocal | Résultat |
|--------|---------------|----------|
| Ouvrir un site | « Ouvre YouTube » | Le site s'ouvre dans le navigateur |
| Rechercher sur le web | « Cherche recettes de crêpes » | Google s'ouvre avec les résultats |
| Ouvrir un fichier | « Ouvre mon document rapport.pdf » | Fichier lancé avec l'app par défaut |
| Lister un dossier | « Qu'est-ce qu'il y a dans Téléchargements ? » | Liste des fichiers annoncée |
| Lire un fichier texte | « Lis le fichier notes.txt » | Contenu lu à voix haute |
| Musique | « Lance cette chanson sur Spotify » | Musique ouverte (navigateur ou ffplay) |

## Ce qu'il ne peut PAS faire

- Supprimer des fichiers
- Modifier ou créer des fichiers
- Exécuter des commandes terminal (`rm`, `sudo`, etc.)

## Prérequis

```bash
sudo apt install ffmpeg portaudio19-dev python3-tk
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Configuration (`.env`)

```env
GEMINI_API_KEY=votre_cle_gemini_ici
GEMINI_MODEL=gemini-2.5-flash
ELEVENLABS_API_KEY=sk_votre_cle_secrete_elevenlabs_ici
ELEVENLABS_VOICE_ID=votre_voice_id_elevenlabs
```

Optionnel :

```env
KOKORO_ALLOWED_PATHS=/home/vous/Documents:/home/vous/Téléchargements
KOKORO_INPUT_DEVICE=0
```

La voix est générée par ElevenLabs avec le modèle multilingue. Choisissez une
voix française dans votre espace ElevenLabs et placez son identifiant dans
`ELEVENLABS_VOICE_ID`. Par défaut : dossier personnel, Téléchargements,
Documents, Bureau, projet.

## Lancer

```bash
.venv/bin/python run.py
```

Une interface de lancement translucide s'ouvre avec un globe animé. Le bouton
ouvre automatiquement le moteur vocal dès que la fenêtre apparaît ; aucun bouton
de démarrage n'est nécessaire.
Le globe affiche des repères de pays dont la taille et l'intensité suivent un
indice économique/numérique indicatif ; le pays au premier plan est affiché dans
le panneau de contrôle. Cet indice n'est pas un classement officiel en temps réel.
Pour lancer le moteur directement sans interface :

```bash
.venv/bin/python kokoro.py
```

Après la préparation du microphone, Kokoro accueille l'utilisateur à voix haute,
écoute directement son expression, répond en français naturel et utilise
la recherche web lorsque la question demande une information actuelle ou vérifiée.

Vérifier le code sans démarrer le micro :

```bash
python3 -m unittest discover -v
python3 -m py_compile kokoro.py kokoro_actions.py
```

Tester uniquement la voix :

```bash
.venv/bin/python kokoro.py --test-voice
```

1. Le lancement accueille l'utilisateur et ouvre directement la session
2. Parlez naturellement
3. Chaque action (web, fichier, musique) **confirme le résultat** à voix haute
4. « Au revoir » ou silence → fin de session

## Exemples de phrases

- « Ouvre google.com »
- « Cherche météo Lubumbashi »
- « Ouvre le fichier rapport.pdf dans Téléchargements »
- « Lis le fichier README.md »
- « Lance la musique https://open.spotify.com/track/... »
- « Quels fichiers sont dans mon Bureau ? »

## Réglages (`kokoro.py`)

| Constante | Défaut | Rôle |
|-----------|--------|------|
| `CONVERSATION_MAX_TURNS` | 12 | Nombre maximal de tours par session |
| `GEMINI_MODEL` | gemini-2.5-flash | Modèle Gemini |
| `ELEVENLABS_VOICE_ID` | — | Voix ElevenLabs utilisée |

Actions détaillées dans `kokoro_actions.py`.
# koko
