"""
Bot Discord pour piloter à distance le serveur Minecraft Sengoku SMP,
hébergé sur Minestrator (API officielle https://mine.sttr.io).

Référence des endpoints utilisés : voir minestrator-api-fr.yaml (spec OpenAPI
fournie par Minestrator), sections "MyBox" et "Server".

Commandes :
- /start  : réactive le serveur (PATCH /mybox/{id_mybox}/server/enable).
- /stop   : désactive le serveur, réservé aux admins (PATCH .../server/disable).
- /status : affiche l'état + les joueurs connectés (GET /server/{id_server}/live).

Tâches de fond :
- Redémarrage automatique périodique (toutes les RESTART_INTERVAL_HOURS heures,
  4h par défaut) : prévient dans le salon, indique les joueurs connectés, puis
  redémarre le serveur même si des joueurs sont en ligne.
- Veille de déconnexion : si le serveur passe hors ligne de façon inattendue,
  un message est envoyé dans le salon pour inviter les joueurs à retaper /start.

Toutes les informations sensibles sont lues depuis des variables d'environnement.
"""

import os
import logging
import asyncio

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MINESTRATOR_API_KEY = os.getenv("MINESTRATOR_API_KEY")
MYBOX_ID = os.getenv("MYBOX_ID")
SERVER_ID = os.getenv("SERVER_ID")

# URL de base officielle de l'API Minestrator (confirmée par minestrator-api-fr.yaml).
MINESTRATOR_API_BASE_URL = os.getenv("MINESTRATOR_API_BASE_URL", "https://mine.sttr.io")

# Salon Discord où poster les annonces automatiques (redémarrage périodique,
# alerte "serveur hors ligne"). Optionnel : si absent, ces deux tâches de fond
# sont simplement désactivées et seules les commandes manuelles fonctionnent.
ANNOUNCE_CHANNEL_ID = os.getenv("ANNOUNCE_CHANNEL_ID")
ANNOUNCE_CHANNEL_ID = int(ANNOUNCE_CHANNEL_ID) if ANNOUNCE_CHANNEL_ID else None

# Intervalle entre deux redémarrages automatiques (en heures).
RESTART_INTERVAL_HOURS = float(os.getenv("RESTART_INTERVAL_HOURS", "4"))

# Délai entre le message d'annonce et le lancement effectif du redémarrage (en secondes).
RESTART_WARNING_SECONDS = int(os.getenv("RESTART_WARNING_SECONDS", "30"))

# Intervalle de la veille "serveur hors ligne" (en secondes). Raisonnable pour
# rester dans le cadre d'un usage normal de l'API (voir CGU Minestrator).
STATUS_POLL_INTERVAL_SECONDS = int(os.getenv("STATUS_POLL_INTERVAL_SECONDS", "120"))

# Rôle Discord autorisé à démarrer le serveur (/start). Vide = tout le monde.
ALLOWED_ROLE_NAME = os.getenv("ALLOWED_ROLE_NAME", "")

# Rôle Discord autorisé à arrêter le serveur (/stop). Vide = utilisateurs avec
# la permission Discord "Gérer le serveur" uniquement.
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "")

if not DISCORD_TOKEN:
    raise RuntimeError("La variable d'environnement DISCORD_TOKEN est manquante.")
if not MINESTRATOR_API_KEY:
    raise RuntimeError("La variable d'environnement MINESTRATOR_API_KEY est manquante.")
if not MYBOX_ID:
    raise RuntimeError("La variable d'environnement MYBOX_ID est manquante.")
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

# Traduction des codes d'erreur "api.error" les plus courants renvoyés par
# l'API (voir minestrator-api-fr.yaml > components > schemas > ApiError).
ERROR_MESSAGES = {
    "API_INVALID_TOKEN": "Clé API invalide ou manquante.",
    "API_FORBIDDEN": "Accès refusé (permissions insuffisantes ou compte suspendu).",
    "API_RATE_LIMITED": "Trop de requêtes envoyées à l'API Minestrator, réessaie dans quelques instants.",
    "API_MISSING_REQUIRED_FIELDS": "Requête invalide : un champ requis est manquant ou incorrect.",
    "API_EMPTY_RESOURCE": "Ressource introuvable (vérifie MYBOX_ID et SERVER_ID).",
    "API_GENERIC_ERROR": "Erreur interne de l'API Minestrator.",
}


class MinestratorAPIError(Exception):
    """Erreur levée quand l'API Minestrator répond avec un problème."""


class MinestratorClient:
    """Client HTTP asynchrone pour l'API Minestrator (https://mine.sttr.io)."""

    def __init__(self, api_key: str, base_url: str):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession(headers=self._headers()) as session:
            async with session.request(
                method, url, json=json_body, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                try:
                    payload = await resp.json()
                except (aiohttp.ContentTypeError, ValueError):
                    payload = None

                if resp.status >= 400:
                    error_code = None
                    if payload and isinstance(payload, dict):
                        error_code = payload.get("api", {}).get("error")
                    message = ERROR_MESSAGES.get(
                        error_code, f"Erreur API Minestrator ({resp.status}) : {error_code or 'inconnue'}"
                    )
                    raise MinestratorAPIError(message)

                return (payload or {}).get("api", {})

    async def enable_server(self) -> None:
        """PATCH /mybox/{id_mybox}/server/enable — réactive le serveur (démarrage)."""
        await self._request(
            "PATCH", f"/mybox/{MYBOX_ID}/server/enable", json_body={"id_server": int(SERVER_ID)}
        )

    async def disable_server(self) -> None:
        """PATCH /mybox/{id_mybox}/server/disable — désactive le serveur (arrêt)."""
        await self._request(
            "PATCH", f"/mybox/{MYBOX_ID}/server/disable", json_body={"id_server": int(SERVER_ID)}
        )

    async def power_action(self, action: str) -> None:
        """PUT /server/{id_server}/poweraction — start / restart / restart10 / stop / stop10 / kill."""
        await self._request(
            "PUT", f"/server/{SERVER_ID}/poweraction", json_body={"poweraction": action}
        )

    async def get_live(self) -> dict:
        """GET /server/{id_server}/live — état courant + joueurs connectés."""
        api = await self._request("GET", f"/server/{SERVER_ID}/live")
        return api.get("data", {})


minestrator = MinestratorClient(MINESTRATOR_API_KEY, MINESTRATOR_API_BASE_URL)

STATE_EMOJIS = {
    "online": "🟢",
    "starting": "🟡",
    "stopping": "🟠",
    "offline": "🔴",
}

STATE_LABELS_FR = {
    "online": "en ligne",
    "starting": "en cours de démarrage",
    "stopping": "en cours d'arrêt",
    "offline": "hors ligne",
}


def format_players(stats: dict) -> str:
    """Construit un petit résumé lisible du nombre de joueurs connectés."""
    players = stats.get("players")
    if not players:
        return "aucune info sur les joueurs"
    current = players.get("current", 0)
    limit = players.get("limit")
    names = players.get("list") or []
    summary = f"{current}/{limit} joueur(s)" if limit is not None else f"{current} joueur(s)"
    if names:
        summary += f" ({', '.join(names)})"
    return summary


# ---------------------------------------------------------------------------
# Bot Discord
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Dernier état connu du serveur, utilisé par la veille "hors ligne" pour ne
# notifier que lors d'une transition (et pas à chaque vérification).
last_known_state: str | None = None


def has_allowed_role(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur a le rôle autorisé pour /start (vide = tout le monde)."""
    if not ALLOWED_ROLE_NAME:
        return True
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(role.name == ALLOWED_ROLE_NAME for role in interaction.user.roles)


def has_admin_permission(interaction: discord.Interaction) -> bool:
    """Vérifie si l'utilisateur peut arrêter le serveur (/stop)."""
    if not isinstance(interaction.user, discord.Member):
        return False
    if ADMIN_ROLE_NAME:
        return any(role.name == ADMIN_ROLE_NAME for role in interaction.user.roles)
    return interaction.user.guild_permissions.manage_guild


@bot.event
async def on_ready():
    logger.info("Connecté en tant que %s (ID: %s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync()
        logger.info("%d commande(s) slash synchronisée(s).", len(synced))
    except Exception:
        logger.exception("Échec de la synchronisation des commandes slash.")

    if ANNOUNCE_CHANNEL_ID:
        if not auto_restart_loop.is_running():
            auto_restart_loop.start()
        if not watch_offline_loop.is_running():
            watch_offline_loop.start()
    else:
        logger.warning(
            "ANNOUNCE_CHANNEL_ID non configuré : redémarrage automatique et "
            "alerte hors-ligne désactivés."
        )


# ---------------------------------------------------------------------------
# Commandes slash
# ---------------------------------------------------------------------------


@bot.tree.command(name="start", description="Démarre le serveur Minecraft Sengoku SMP")
async def start(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        live = await minestrator.get_live()
        state = live.get("state", "offline")
        if state in ("online", "starting"):
            await interaction.followup.send(
                f"ℹ️ Le serveur est déjà **{STATE_LABELS_FR.get(state, state)}**, pas besoin de le redémarrer."
            )
            return

        await minestrator.enable_server()
        await interaction.followup.send(
            "✅ Démarrage du serveur demandé avec succès ! Ça devrait être en ligne dans quelques instants."
        )
    except MinestratorAPIError as e:
        await interaction.followup.send(f"⚠️ Impossible de démarrer le serveur : {e}")
    except aiohttp.ClientError:
        logger.exception("Erreur réseau lors de l'appel à l'API Minestrator (start).")
        await interaction.followup.send("❌ Impossible de contacter l'API Minestrator pour le moment. Réessaie plus tard.")
    except Exception:
        logger.exception("Erreur inattendue lors de la commande /start.")
        await interaction.followup.send("❌ Une erreur inattendue est survenue.")


@bot.tree.command(name="stop", description="Arrête le serveur Minecraft Sengoku SMP (admins uniquement)")
async def stop(interaction: discord.Interaction):
    if not has_admin_permission(interaction):
        await interaction.response.send_message(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        await minestrator.disable_server()
        await interaction.followup.send("🛑 Arrêt du serveur demandé avec succès.")
    except MinestratorAPIError as e:
        await interaction.followup.send(f"⚠️ Impossible d'arrêter le serveur : {e}")
    except aiohttp.ClientError:
        logger.exception("Erreur réseau lors de l'appel à l'API Minestrator (stop).")
        await interaction.followup.send("❌ Impossible de contacter l'API Minestrator pour le moment. Réessaie plus tard.")
    except Exception:
        logger.exception("Erreur inattendue lors de la commande /stop.")
        await interaction.followup.send("❌ Une erreur inattendue est survenue.")


@bot.tree.command(name="status", description="Affiche l'état actuel du serveur Minecraft Sengoku SMP")
async def status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        live = await minestrator.get_live()
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

    state = live.get("state", "offline")
    emoji = STATE_EMOJIS.get(state, "⚪")
    label = STATE_LABELS_FR.get(state, state)
    stats = live.get("stats", {})

    message = f"{emoji} Statut du serveur : **{label}**"
    if state == "online":
        message += f"\n👥 Joueurs connectés : {format_players(stats)}"
    await interaction.followup.send(message)


# ---------------------------------------------------------------------------
# Tâches de fond
# ---------------------------------------------------------------------------


async def _get_announce_channel() -> discord.abc.Messageable | None:
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ANNOUNCE_CHANNEL_ID)
        except discord.DiscordException:
            logger.exception("Impossible de récupérer le salon d'annonces (ANNOUNCE_CHANNEL_ID=%s).", ANNOUNCE_CHANNEL_ID)
            return None
    return channel


@tasks.loop(hours=RESTART_INTERVAL_HOURS)
async def auto_restart_loop():
    """Redémarre le serveur périodiquement, même si des joueurs sont connectés."""
    channel = await _get_announce_channel()
    if channel is None:
        return

    try:
        live = await minestrator.get_live()
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Impossible de vérifier l'état du serveur avant le redémarrage automatique.")
        return

    state = live.get("state", "offline")
    if state != "online":
        # Rien à redémarrer si le serveur n'est pas en ligne.
        return

    stats = live.get("stats", {})
    players_summary = format_players(stats)

    await channel.send(
        f"🔄 Redémarrage automatique du serveur dans {RESTART_WARNING_SECONDS} secondes "
        f"(maintenance périodique toutes les {RESTART_INTERVAL_HOURS:g}h).\n"
        f"👥 Joueurs actuellement connectés : {players_summary}.\n"
        "Le redémarrage a lieu même si des joueurs sont en ligne, désolé pour la gêne !"
    )

    await asyncio.sleep(RESTART_WARNING_SECONDS)

    try:
        await minestrator.power_action("restart10")
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Échec de l'appel poweraction restart10 lors du redémarrage automatique.")
        await channel.send("⚠️ Le redémarrage automatique a échoué. Un admin devra vérifier le serveur.")
        return

    # On attend que le serveur revienne en ligne (poweraction restart10 bloque
    # déjà ~10s, on laisse ensuite un peu de marge pour le boot du serveur).
    back_online = False
    for _ in range(18):  # jusqu'à ~90s d'attente supplémentaire
        await asyncio.sleep(5)
        try:
            live = await minestrator.get_live()
        except (MinestratorAPIError, aiohttp.ClientError):
            continue
        if live.get("state") == "online":
            back_online = True
            break

    if back_online:
        await channel.send("✅ Redémarrage terminé, le serveur est de nouveau en ligne.")
    else:
        await channel.send(
            "🔴 Le serveur ne semble pas être remonté automatiquement après le redémarrage. "
            "Retapez `/start` pour le relancer !"
        )


@tasks.loop(seconds=STATUS_POLL_INTERVAL_SECONDS)
async def watch_offline_loop():
    """Alerte le salon si le serveur passe hors ligne de façon inattendue."""
    global last_known_state

    channel = await _get_announce_channel()
    if channel is None:
        return

    try:
        live = await minestrator.get_live()
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Erreur lors de la veille de statut du serveur.")
        return

    state = live.get("state", "offline")

    if last_known_state in ("online", "starting") and state == "offline":
        await channel.send(
            "🔴 Le serveur Sengoku SMP est hors ligne. Retapez `/start` pour le relancer !"
        )

    last_known_state = state


@auto_restart_loop.before_loop
@watch_offline_loop.before_loop
async def _before_loops():
    await bot.wait_until_ready()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
