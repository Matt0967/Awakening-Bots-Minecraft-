"""
Bot Discord pour piloter à distance un serveur Minecraft hébergé sur Minestrator.

Fonctionnalités :
- /start  : démarre le serveur Minecraft via l'API Minestrator (requête POST).
- /status : renvoie l'état actuel du serveur (en ligne / hors ligne / en démarrage).

Toutes les informations sensibles (token Discord, clé API, ID du serveur) sont
lues depuis des variables d'environnement (fichier .env en local, ou variables
d'environnement configurées sur la plateforme d'hébergement en production).
"""

import os
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Charge les variables définies dans le fichier .env (utile en local uniquement ;
# en production, l'hébergeur fournit directement les variables d'environnement).
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MINESTRATOR_API_KEY = os.getenv("MINESTRATOR_API_KEY")
SERVER_ID = os.getenv("SERVER_ID")

# URL de base de l'API Minestrator.
# ⚠️ À VÉRIFIER : Minestrator ne publie pas (à ma connaissance) une documentation
# publique stable de son API. Cette valeur par défaut est une hypothèse basée sur
# les conventions REST classiques ("panel.minestrator.com/api/..."). Avant de
# lancer le bot, connecte-toi à ton panel Minestrator, ouvre la section API /
# Développeur (ou contacte le support) pour confirmer :
#   1) l'URL de base réelle de l'API
#   2) le chemin exact pour démarrer un serveur et pour récupérer son statut
#   3) le nom du header d'authentification attendu (Authorization, X-Api-Key, etc.)
# Tu peux surcharger l'URL de base sans toucher au code via la variable
# d'environnement MINESTRATOR_API_BASE_URL.
MINESTRATOR_API_BASE_URL = os.getenv(
    "MINESTRATOR_API_BASE_URL", "https://panel.minestrator.com/api"
)

# Chemins des endpoints (relatifs à MINESTRATOR_API_BASE_URL).
# Adapte-les si la documentation/le support Minestrator te donne des chemins différents.
START_ENDPOINT = f"/servers/{SERVER_ID}/power/start"
STATUS_ENDPOINT = f"/servers/{SERVER_ID}/status"

# Rôle Discord autorisé à utiliser les commandes (optionnel).
# Si tu veux restreindre l'accès à un rôle précis, mets son nom exact ici,
# sinon laisse la variable d'environnement vide pour autoriser tout le monde.
ALLOWED_ROLE_NAME = os.getenv("ALLOWED_ROLE_NAME", "")

# Vérification au démarrage : on préfère planter tout de suite avec un message
# clair plutôt que de démarrer un bot mal configuré.
if not DISCORD_TOKEN:
    raise RuntimeError("La variable d'environnement DISCORD_TOKEN est manquante.")
if not MINESTRATOR_API_KEY:
    raise RuntimeError("La variable d'environnement MINESTRATOR_API_KEY est manquante.")
if not SERVER_ID:
    raise RuntimeError("La variable d'environnement SERVER_ID est manquante.")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sengoku-bot")

# ---------------------------------------------------------------------------
# Client API Minestrator
# ---------------------------------------------------------------------------


class MinestratorAPIError(Exception):
    """Erreur levée quand l'API Minestrator répond avec un problème."""


class MinestratorClient:
    """Petit client HTTP asynchrone pour dialoguer avec l'API Minestrator."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict:
        # ⚠️ À VÉRIFIER : certaines API utilisent "Authorization: Bearer <clé>",
        # d'autres un header personnalisé comme "X-Api-Key". Ajuste si besoin.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    async def start_server(self) -> None:
        """Envoie une requête POST pour démarrer le serveur."""
        url = f"{self._base_url}{START_ENDPOINT}"
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            async with session.post(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 409:
                    raise MinestratorAPIError("Le serveur est déjà démarré ou en cours de démarrage.")
                if resp.status == 401 or resp.status == 403:
                    raise MinestratorAPIError("Clé API invalide ou accès refusé par Minestrator.")
                if resp.status >= 400:
                    body = await resp.text()
                    raise MinestratorAPIError(
                        f"L'API Minestrator a renvoyé une erreur ({resp.status}) : {body[:200]}"
                    )

    async def get_status(self) -> str:
        """Envoie une requête GET et renvoie le statut brut du serveur."""
        url = f"{self._base_url}{STATUS_ENDPOINT}"
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 401 or resp.status == 403:
                    raise MinestratorAPIError("Clé API invalide ou accès refusé par Minestrator.")
                if resp.status >= 400:
                    body = await resp.text()
                    raise MinestratorAPIError(
                        f"L'API Minestrator a renvoyé une erreur ({resp.status}) : {body[:200]}"
                    )
                data = await resp.json()
                # ⚠️ À VÉRIFIER : adapte la clé "state" au nom réel du champ
                # renvoyé par l'API Minestrator (peut être "status", "state", etc.).
                return str(data.get("state", "unknown"))


minestrator = MinestratorClient(MINESTRATOR_API_KEY, MINESTRATOR_API_BASE_URL)

# ---------------------------------------------------------------------------
# Bot Discord
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def has_allowed_role(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur a le rôle autorisé (si un rôle a été configuré)."""
    if not ALLOWED_ROLE_NAME:
        return True
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(role.name == ALLOWED_ROLE_NAME for role in interaction.user.roles)


@bot.event
async def on_ready():
    logger.info("Connecté en tant que %s (ID: %s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync()
        logger.info("%d commande(s) slash synchronisée(s).", len(synced))
    except Exception:
        logger.exception("Échec de la synchronisation des commandes slash.")


@bot.tree.command(name="start", description="Démarre le serveur Minecraft Sengoku SMP")
async def start(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )
        return

    # On répond immédiatement pour éviter le timeout de 3s de Discord pendant
    # que la requête vers Minestrator est en cours.
    await interaction.response.defer(thinking=True)

    try:
        await minestrator.start_server()
        await interaction.followup.send("✅ Démarrage du serveur demandé avec succès ! Ça devrait être en ligne dans quelques instants.")
    except MinestratorAPIError as e:
        await interaction.followup.send(f"⚠️ Impossible de démarrer le serveur : {e}")
    except aiohttp.ClientError:
        logger.exception("Erreur réseau lors de l'appel à l'API Minestrator (start).")
        await interaction.followup.send("❌ Impossible de contacter l'API Minestrator pour le moment. Réessaie plus tard.")
    except Exception:
        logger.exception("Erreur inattendue lors de la commande /start.")
        await interaction.followup.send("❌ Une erreur inattendue est survenue.")


@bot.tree.command(name="status", description="Affiche l'état actuel du serveur Minecraft Sengoku SMP")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        state = await minestrator.get_status()
    except MinestratorAPIError as e:
        await interaction.followup.send(f"⚠️ Impossible de récupérer le statut : {e}")
        return
    except aiohttp.ClientError:
        logger.exception("Erreur réseau lors de l'appel à l'API Minestrator (status).")
        await interaction.followup.send("❌ Impossible de contacter l'API Minestrator pour le moment. Réessaie plus tard.")
        return
    except Exception:
        logger.exception("Erreur inattendue lors de la commande /status.")
        await interaction.followup.send("❌ Une erreur inattendue est survenue.")
        return

    # ⚠️ À VÉRIFIER : adapte ces valeurs aux libellés réels renvoyés par l'API
    # Minestrator (ex: "running", "offline", "starting"...).
    emojis = {
        "running": "🟢",
        "online": "🟢",
        "offline": "🔴",
        "stopped": "🔴",
        "starting": "🟡",
    }
    emoji = emojis.get(state.lower(), "⚪")
    await interaction.followup.send(f"{emoji} Statut du serveur : **{state}**")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
