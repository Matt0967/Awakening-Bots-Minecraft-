"""
Bot Discord pour piloter à distance le serveur Minecraft Sengoku SMP,
hébergé sur Minestrator (API officielle https://mine.sttr.io).

Référence des endpoints utilisés : voir minestrator-api-fr.yaml (spec OpenAPI
fournie par Minestrator), section "Server".

IMPORTANT — offre gratuite : le support Minestrator a confirmé le 2026-09-03
que piloter le démarrage du serveur via l'API sur une offre gratuite est
interdit (PUT /poweraction renvoie 403 API_FORBIDDEN, et ajouter un en-tête
Origin pour passer outre est considéré comme un contournement). Les commandes
d'alimentation sont donc désactivées par défaut : voir POWER_ACTIONS_ENABLED,
à ne réactiver qu'avec une offre payante. Le reste (statut, statistiques) est
en lecture seule et n'est pas concerné.

Commandes (start/restart/status ouvertes à tous les membres, stop réservé aux
admins) :
- /start   : démarre le serveur (PUT .../poweraction "start"). Désactivée.
- /restart : redémarre le serveur en cours (PUT .../poweraction "restart10"). Désactivée.
- /stop    : arrête le serveur, réservé aux admins (PUT .../poweraction "stop10"). Désactivée.
- /status  : affiche l'état + les joueurs connectés (GET /server/{id_server}/live).

Tâches de fond :
- Redémarrage automatique périodique (toutes les RESTART_INTERVAL_HOURS heures,
  4h par défaut) : prévient dans le salon, indique les joueurs connectés, puis
  redémarre le serveur même si des joueurs sont en ligne. Désactivé tant que
  POWER_ACTIONS_ENABLED est à false.
- Veille de déconnexion : si le serveur passe hors ligne de façon inattendue,
  un message est envoyé dans le salon pour prévenir les joueurs.
- Panneau de statistiques en direct : un message (embed) mis à jour
  périodiquement dans un salon dédié, avec l'état, le CPU, la RAM, le disque,
  les joueurs connectés et l'uptime du serveur.

Toutes les informations sensibles sont lues depuis des variables d'environnement.
"""

import os
import logging
import asyncio

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MINESTRATOR_API_KEY = os.getenv("MINESTRATOR_API_KEY")
SERVER_ID = os.getenv("SERVER_ID")

# URL de base officielle de l'API Minestrator (confirmée par minestrator-api-fr.yaml).
MINESTRATOR_API_BASE_URL = os.getenv("MINESTRATOR_API_BASE_URL", "https://mine.sttr.io")

# Salon Discord où poster les annonces automatiques (redémarrage périodique,
# alerte "serveur hors ligne"). Optionnel : si absent, ces deux tâches de fond
# sont simplement désactivées et seules les commandes manuelles fonctionnent.
ANNOUNCE_CHANNEL_ID = os.getenv("ANNOUNCE_CHANNEL_ID")
ANNOUNCE_CHANNEL_ID = int(ANNOUNCE_CHANNEL_ID) if ANNOUNCE_CHANNEL_ID else None

# Salon Discord où poster/actualiser le panneau de statistiques en direct
# (CPU, RAM, disque, joueurs, uptime). Optionnel : sans valeur, retombe sur
# ANNOUNCE_CHANNEL_ID ; si aucun des deux n'est défini, le panneau est désactivé.
STATS_CHANNEL_ID = os.getenv("STATS_CHANNEL_ID")
STATS_CHANNEL_ID = int(STATS_CHANNEL_ID) if STATS_CHANNEL_ID else ANNOUNCE_CHANNEL_ID

# Intervalle entre deux redémarrages automatiques (en heures).
RESTART_INTERVAL_HOURS = float(os.getenv("RESTART_INTERVAL_HOURS", "4"))

# Délai entre le message d'annonce et le lancement effectif du redémarrage
# automatique (en secondes). Un /restart manuel se lance lui immédiatement.
RESTART_WARNING_SECONDS = int(os.getenv("RESTART_WARNING_SECONDS", "30"))

# Intervalle de la veille "serveur hors ligne" (en secondes). Raisonnable pour
# rester dans le cadre d'un usage normal de l'API (voir CGU Minestrator).
STATUS_POLL_INTERVAL_SECONDS = int(os.getenv("STATUS_POLL_INTERVAL_SECONDS", "120"))

# Intervalle de rafraîchissement du panneau de statistiques (en secondes).
STATS_UPDATE_INTERVAL_SECONDS = int(os.getenv("STATS_UPDATE_INTERVAL_SECONDS", "60"))

# Actions d'alimentation (start / restart / stop) via l'API.
#
# Le support Minestrator a répondu le 2026-09-03 que sur les offres gratuites,
# "tout contournement du démarrage manuel depuis le panel est strictement
# interdit" : /poweraction n'est utilisable qu'avec une offre payante. Le
# drapeau est donc à false par défaut — le bot reste alors en lecture seule
# (/status et panneau de statistiques), ce qui n'est pas concerné.
#
# À repasser à true uniquement après être passé sur une offre payante.
POWER_ACTIONS_ENABLED = os.getenv("POWER_ACTIONS_ENABLED", "false").lower() in ("1", "true", "yes")

# Message affiché quand une commande d'alimentation est désactivée.
POWER_ACTIONS_DISABLED_MESSAGE = (
    "🔒 Cette commande est désactivée : l'offre gratuite Minestrator ne permet "
    "pas de piloter le serveur via l'API. Le démarrage doit se faire depuis le "
    "panel Minestrator."
)

# Rôle Discord autorisé à arrêter le serveur (/stop). Vide = utilisateurs avec
# la permission Discord "Gérer le serveur" uniquement. /start, /restart et
# /status restent volontairement ouverts à tous les membres, sans restriction.
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "")

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

# Traduction des codes d'erreur "api.error" les plus courants renvoyés par
# l'API (voir minestrator-api-fr.yaml > components > schemas > ApiError).
ERROR_MESSAGES = {
    "API_INVALID_TOKEN": "Clé API invalide ou manquante.",
    "API_FORBIDDEN": "Accès refusé (permissions insuffisantes ou compte suspendu).",
    "API_RATE_LIMITED": "Trop de requêtes envoyées à l'API Minestrator, réessaie dans quelques instants.",
    "API_MISSING_REQUIRED_FIELDS": "Requête invalide : un champ requis est manquant ou incorrect.",
    "API_EMPTY_RESOURCE": "Ressource introuvable (vérifie SERVER_ID).",
    "API_GENERIC_ERROR": "Erreur interne de l'API Minestrator.",
    "API_MYBOX_FREE_FORBIDDEN": (
        "Action bloquée par Minestrator sur les MyBox gratuites. "
        "Démarre/arrête le serveur depuis le panel, ou contacte le support Minestrator "
        "pour confirmer si l'offre gratuite permet ça via l'API."
    ),
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
            # Aucun en-tête Origin/Referer : le support Minestrator a confirmé
            # le 2026-09-03 que l'ajouter pour passer le 403 API_FORBIDDEN sur
            # /poweraction constitue un contournement interdit sur l'offre
            # gratuite. Voir POWER_ACTIONS_ENABLED plus haut.
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

# Diagnostic au démarrage : n'affiche jamais le secret en entier, juste de quoi
# vérifier dans les logs (Railway, etc.) que les bonnes valeurs sont chargées
# sans avoir à comparer des captures d'écran à la main.
logger.info(
    "Config chargée : SERVER_ID=%s, MINESTRATOR_API_KEY=%s… (%d caractères), "
    "ANNOUNCE_CHANNEL_ID=%s, STATS_CHANNEL_ID=%s",
    SERVER_ID,
    MINESTRATOR_API_KEY[:4],
    len(MINESTRATOR_API_KEY),
    ANNOUNCE_CHANNEL_ID,
    STATS_CHANNEL_ID,
)

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
        if POWER_ACTIONS_ENABLED:
            if not auto_restart_loop.is_running():
                auto_restart_loop.start()
        else:
            logger.warning(
                "POWER_ACTIONS_ENABLED=false : redémarrage automatique désactivé "
                "(offre gratuite Minestrator, actions d'alimentation interdites via l'API)."
            )
        if not watch_offline_loop.is_running():
            watch_offline_loop.start()
    else:
        logger.warning(
            "ANNOUNCE_CHANNEL_ID non configuré : redémarrage automatique et "
            "alerte hors-ligne désactivés."
        )

    if STATS_CHANNEL_ID:
        if not stats_panel_loop.is_running():
            stats_panel_loop.start()
    else:
        logger.warning("STATS_CHANNEL_ID non configuré : panneau de statistiques désactivé.")


# ---------------------------------------------------------------------------
# Commandes slash
# ---------------------------------------------------------------------------


async def refuse_if_power_actions_disabled(interaction: discord.Interaction) -> bool:
    """Répond et renvoie True si les actions d'alimentation sont interdites."""
    if POWER_ACTIONS_ENABLED:
        return False
    await interaction.response.send_message(POWER_ACTIONS_DISABLED_MESSAGE, ephemeral=True)
    return True


@bot.tree.command(name="start", description="Démarre le serveur Minecraft Sengoku SMP")
async def start(interaction: discord.Interaction):
    # Ouvert à tous les membres, sans restriction de rôle.
    if await refuse_if_power_actions_disabled(interaction):
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

        await minestrator.power_action("start")
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


@bot.tree.command(name="restart", description="Redémarre le serveur Minecraft Sengoku SMP")
async def restart(interaction: discord.Interaction):
    # Ouvert à tous les membres, sans restriction de rôle.
    if await refuse_if_power_actions_disabled(interaction):
        return
    await interaction.response.defer(thinking=True)

    try:
        live = await minestrator.get_live()
    except MinestratorAPIError as e:
        await interaction.followup.send(f"⚠️ Impossible de vérifier l'état du serveur : {e}")
        return
    except aiohttp.ClientError:
        logger.exception("Erreur réseau lors de l'appel à l'API Minestrator (restart).")
        await interaction.followup.send("❌ Impossible de contacter l'API Minestrator pour le moment. Réessaie plus tard.")
        return
    except Exception:
        logger.exception("Erreur inattendue lors de la commande /restart.")
        await interaction.followup.send("❌ Une erreur inattendue est survenue.")
        return

    state = live.get("state", "offline")
    if state == "offline":
        await interaction.followup.send("ℹ️ Le serveur est hors ligne. Démarre-le depuis le panel Minestrator.")
        return
    if state in ("starting", "stopping"):
        await interaction.followup.send(
            f"ℹ️ Le serveur est **{STATE_LABELS_FR.get(state, state)}**, réessaie dans un instant."
        )
        return

    # state == "online" : on redémarre tout de suite (poweraction restart10
    # diffuse déjà son propre compte à rebours de 10s en jeu, pas besoin d'attendre en plus).
    await execute_restart_sequence(
        interaction.followup.send,
        live.get("stats", {}),
        wait_seconds=0,
        intro=f"🔄 Redémarrage du serveur demandé par {interaction.user.mention}.",
    )


@bot.tree.command(name="stop", description="Arrête le serveur Minecraft Sengoku SMP (admins uniquement)")
async def stop(interaction: discord.Interaction):
    if await refuse_if_power_actions_disabled(interaction):
        return
    if not has_admin_permission(interaction):
        await interaction.response.send_message(
            "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    try:
        await minestrator.power_action("stop10")
        await interaction.followup.send(
            "🛑 Arrêt du serveur demandé (compte à rebours de 10s diffusé en jeu)."
        )
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


async def _get_channel(channel_id: int | None) -> discord.abc.Messageable | None:
    if channel_id is None:
        return None
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.DiscordException:
            logger.exception("Impossible de récupérer le salon (channel_id=%s).", channel_id)
            return None
    return channel


async def execute_restart_sequence(send, stats: dict, *, wait_seconds: int, intro: str) -> None:
    """Prévient, patiente éventuellement, redémarre le serveur puis attend son retour en ligne.

    `send` est un callable async (channel.send ou interaction.followup.send) qui
    prend un simple message texte. Suppose que le serveur est déjà `online`.
    """
    players_summary = format_players(stats)
    await send(f"{intro}\n👥 Joueurs actuellement connectés : {players_summary}.")

    if wait_seconds:
        await asyncio.sleep(wait_seconds)

    try:
        await minestrator.power_action("restart10")
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Échec de l'appel poweraction restart10.")
        await send("⚠️ Le redémarrage a échoué. Réessaie plus tard ou préviens un admin.")
        return

    # On attend que le serveur revienne en ligne (poweraction restart10 bloque
    # déjà ~10s côté API, on laisse ensuite un peu de marge pour le boot du serveur).
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
        await send("✅ Redémarrage terminé, le serveur est de nouveau en ligne.")
    else:
        await send(
            "🔴 Le serveur ne semble pas être remonté automatiquement après le redémarrage. "
            "Relance-le depuis le panel Minestrator."
        )


@tasks.loop(hours=RESTART_INTERVAL_HOURS)
async def auto_restart_loop():
    """Redémarre le serveur périodiquement, même si des joueurs sont connectés."""
    channel = await _get_channel(ANNOUNCE_CHANNEL_ID)
    if channel is None:
        return

    try:
        live = await minestrator.get_live()
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Impossible de vérifier l'état du serveur avant le redémarrage automatique.")
        return

    if live.get("state") != "online":
        # Rien à redémarrer si le serveur n'est pas en ligne.
        return

    await execute_restart_sequence(
        channel.send,
        live.get("stats", {}),
        wait_seconds=RESTART_WARNING_SECONDS,
        intro=(
            f"🔄 Redémarrage automatique du serveur dans {RESTART_WARNING_SECONDS} secondes "
            f"(maintenance périodique toutes les {RESTART_INTERVAL_HOURS:g}h). "
            "Le redémarrage a lieu même si des joueurs sont en ligne, désolé pour la gêne !"
        ),
    )


@tasks.loop(seconds=STATUS_POLL_INTERVAL_SECONDS)
async def watch_offline_loop():
    """Alerte le salon si le serveur passe hors ligne de façon inattendue."""
    global last_known_state

    channel = await _get_channel(ANNOUNCE_CHANNEL_ID)
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
            "🔴 Le serveur Sengoku SMP est hors ligne. Un administrateur doit le relancer depuis le panel Minestrator."
        )

    last_known_state = state


# --- Panneau de statistiques en direct -------------------------------------

STATS_EMBED_TITLE = "📊 Sengoku SMP — Performances en direct"

STATE_COLORS = {
    "online": discord.Color.green(),
    "starting": discord.Color.gold(),
    "stopping": discord.Color.orange(),
    "offline": discord.Color.red(),
}

# Message du panneau, mis en cache une fois trouvé/créé pour éviter de
# reparcourir l'historique du salon à chaque rafraîchissement.
stats_message: discord.Message | None = None


def build_stats_embed(live: dict) -> discord.Embed:
    state = live.get("state", "offline")
    stats = live.get("stats", {})

    embed = discord.Embed(
        title=STATS_EMBED_TITLE,
        color=STATE_COLORS.get(state, discord.Color.greyple()),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="État",
        value=f"{STATE_EMOJIS.get(state, '⚪')} {STATE_LABELS_FR.get(state, state)}",
        inline=False,
    )

    cpu = stats.get("cpu")
    if cpu:
        embed.add_field(
            name="CPU",
            value=f"{cpu.get('percent', 0)}% (limite : {cpu.get('limit', 0)} centièmes de cœur)",
            inline=True,
        )
    memory = stats.get("memory")
    if memory:
        embed.add_field(
            name="Mémoire",
            value=f"{memory.get('current', 0)} / {memory.get('limit', 0)} Mo ({memory.get('percent', 0)}%)",
            inline=True,
        )
    disk = stats.get("disk")
    if disk:
        embed.add_field(
            name="Disque",
            value=f"{disk.get('current', 0)} / {disk.get('limit', 0)} Mo ({disk.get('percent', 0)}%)",
            inline=True,
        )

    if state == "online":
        embed.add_field(name="Joueurs", value=format_players(stats), inline=False)
        uptime = stats.get("uptime")
        if uptime:
            embed.add_field(
                name="Uptime",
                value=f"{uptime.get('days', 0)}j {uptime.get('hours', 0)}h {uptime.get('minutes', 0)}min",
                inline=True,
            )

    embed.set_footer(text="Dernière mise à jour")
    return embed


async def _get_stats_message(channel: discord.abc.Messageable) -> discord.Message | None:
    """Retrouve le message du panneau déjà posté par le bot, ou en crée un nouveau."""
    global stats_message
    if stats_message is not None:
        return stats_message

    try:
        async for msg in channel.history(limit=20):
            if msg.author == bot.user and msg.embeds and msg.embeds[0].title == STATS_EMBED_TITLE:
                stats_message = msg
                return stats_message
    except discord.DiscordException:
        logger.exception("Impossible de parcourir l'historique du salon de statistiques.")
        return None

    try:
        stats_message = await channel.send(embed=discord.Embed(title=STATS_EMBED_TITLE, description="Chargement…"))
    except discord.DiscordException:
        logger.exception("Impossible de créer le message du panneau de statistiques.")
        return None
    return stats_message


@tasks.loop(seconds=STATS_UPDATE_INTERVAL_SECONDS)
async def stats_panel_loop():
    """Met à jour périodiquement l'embed de statistiques en direct."""
    global stats_message

    channel = await _get_channel(STATS_CHANNEL_ID)
    if channel is None:
        return

    try:
        live = await minestrator.get_live()
    except (MinestratorAPIError, aiohttp.ClientError):
        logger.exception("Erreur lors de la récupération des statistiques pour le panneau.")
        return

    message = await _get_stats_message(channel)
    if message is None:
        return

    try:
        await message.edit(embed=build_stats_embed(live))
    except discord.DiscordException:
        logger.exception("Impossible de mettre à jour le message du panneau de statistiques.")
        stats_message = None  # on retentera une recherche/création au prochain tour


@auto_restart_loop.before_loop
@watch_offline_loop.before_loop
@stats_panel_loop.before_loop
async def _before_loops():
    await bot.wait_until_ready()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
