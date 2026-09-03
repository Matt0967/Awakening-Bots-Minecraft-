# Sengoku SMP — Bot Discord de contrôle serveur (Minestrator)

Bot Discord affichant l'état du serveur Minecraft Sengoku SMP (hébergé sur
Minestrator) dans Discord, et — **sur une offre payante uniquement** — permettant
à tes joueurs de le démarrer sans accès au panel d'administration.

## ⚠️ Offre gratuite : commandes d'alimentation désactivées

Le support Minestrator a confirmé le **3 septembre 2026** que sur les offres
gratuites, **tout contournement du démarrage manuel depuis le panel est
strictement interdit**. Concrètement :

- `PUT /server/{id_server}/poweraction` répond `403 API_FORBIDDEN` sans en-tête
  `Origin` pointant vers `minestrator.com` ;
- ajouter cet en-tête pour passer outre est considéré par Minestrator comme un
  **contournement volontaire**, passible de suspension du compte.

Le bot n'envoie donc plus cet en-tête, et les commandes `/start`, `/restart` et
`/stop` ainsi que le redémarrage automatique sont **désactivés par défaut**
(`POWER_ACTIONS_ENABLED=false`). Le serveur doit être démarré depuis le panel
Minestrator.

Les fonctions de lecture (`/status`, panneau de statistiques) ne sont pas
concernées et continuent de fonctionner.

Si tu passes sur une offre payante — Minestrator indique que **toutes** leurs
offres payantes autorisent cet usage de l'API — mets `POWER_ACTIONS_ENABLED=true`
dans ton `.env` pour réactiver l'ensemble.

## Commandes

- `/status` — affiche l'état actuel du serveur et les joueurs connectés (`GET /server/{id_server}/live`). Ouvert à tous.
- `/start` — démarre le serveur (`PUT /server/{id_server}/poweraction` avec `"start"`). Ouvert à tous les membres. **Désactivé sur offre gratuite.**
- `/restart` — redémarre le serveur en cours (`PUT .../poweraction` avec `"restart10"`). Ouvert à tous les membres. **Désactivé sur offre gratuite.**
- `/stop` — arrête le serveur (`PUT .../poweraction` avec `"stop10"`). Réservé aux admins. **Désactivé sur offre gratuite.**

Quand elles sont actives, `/start` et `/restart` sont volontairement accessibles
à n'importe quel membre du serveur Discord, sans rôle particulier — c'est tout
l'intérêt du bot : permettre à tes joueurs d'allumer/redémarrer le serveur sans
accès au panel. Seul `/stop` est restreint (voir "Permissions Discord
nécessaires" plus bas).

Le bot fait aussi tourner trois tâches de fond (voir sections "Redémarrage
automatique" et "Panneau de statistiques" plus bas) : un redémarrage
périodique toutes les 4h (désactivé avec les commandes d'alimentation), une
alerte dans le salon Discord si le serveur tombe hors ligne de façon
inattendue, et un panneau de statistiques mis à jour en direct.

La documentation officielle de l'API (spec OpenAPI) est incluse dans ce dépôt :
[`minestrator-api-fr.yaml`](./minestrator-api-fr.yaml). C'est la source de
vérité si Minestrator fait évoluer son API — `main.py` s'appuie exactement
dessus (endpoints, headers, schémas de réponse/erreur).

## 1. Récupérer ta clé API et ton ID de serveur sur Minestrator

1. Connecte-toi sur https://minestrator.com puis va dans
   **Compte → Clés API** (directement : https://minestrator.com/my/account?section=api).
2. Génère une clé API et **copie-la immédiatement** — elle est affichée **déjà
   encodée** : colle-la telle quelle dans `.env`, ne la ré-encode pas. Garde-la
   secrète, elle donne un accès équivalent à ton mot de passe pour les actions
   autorisées.
3. **Important (offre gratuite)** : l'API est accessible en lecture, mais les
   actions d'alimentation (`poweraction`) sont réservées aux offres payantes —
   voir l'encadré en haut de ce README. Un usage abusif (polling trop fréquent,
   etc.) peut par ailleurs faire désactiver l'accès API : reste dans les
   intervalles par défaut du bot (`STATUS_POLL_INTERVAL_SECONDS`,
   `STATS_UPDATE_INTERVAL_SECONDS`) sauf besoin réel.
4. Récupère ton **`SERVER_ID`** : sur la page de ton serveur Minecraft dans le
   panel, l'ID apparaît dans l'URL (ex: `.../server/67890/...`). Attention à
   ne pas confondre avec l'ID de la MyBox (`.../mybox/12345/...`) qui apparaît
   sur une autre page — c'est bien le second, spécifique au serveur, qu'il
   faut utiliser.

## 2. Installer et tester le bot en local

### Prérequis

- Python 3.10 ou supérieur installé.
- Un compte sur le [Discord Developer Portal](https://discord.com/developers/applications).

### Créer l'application Discord

1. Va sur https://discord.com/developers/applications > **New Application**.
2. Dans l'onglet **Bot**, clique sur **Reset Token** pour générer ton
   `DISCORD_TOKEN` (à garder secret).
3. Toujours dans **Bot**, active si besoin les **Privileged Gateway Intents**
   (pour ce bot, aucun intent privilégié n'est nécessaire — seules les slash
   commands sont utilisées).
4. Dans l'onglet **OAuth2 > URL Generator** :
   - Scopes : coche `bot` et `applications.commands`.
   - Permissions du bot (voir section "Permissions nécessaires" plus bas).
   - Copie l'URL générée et ouvre-la dans un navigateur pour inviter le bot sur
     ton serveur Discord.

### Installer les dépendances

```bash
cd "bot discord et minecraft"
python3 -m venv venv
source venv/bin/activate        # sous Windows : venv\Scripts\activate
pip install -r requirements.txt
```

### Configurer les secrets

Crée un fichier `.env` à la racine du projet avec au minimum :

```
DISCORD_TOKEN=
MINESTRATOR_API_KEY=
SERVER_ID=
ANNOUNCE_CHANNEL_ID=
```

Toutes les autres variables (`POWER_ACTIONS_ENABLED`, `STATS_CHANNEL_ID`,
`RESTART_INTERVAL_HOURS`, `RESTART_WARNING_SECONDS`,
`STATUS_POLL_INTERVAL_SECONDS`, `STATS_UPDATE_INTERVAL_SECONDS`,
`ADMIN_ROLE_NAME`, `MINESTRATOR_API_BASE_URL`) sont optionnelles — voir leur description dans `main.py` (section
Configuration) si tu veux les personnaliser.

Ce fichier `.env` est ignoré par Git (voir `.gitignore`) — il ne sera jamais
envoyé sur GitHub.

### Lancer le bot

```bash
python main.py
```

Si tout fonctionne, tu verras dans le terminal `Connecté en tant que ...` puis
`X commande(s) slash synchronisée(s).`. Va sur ton serveur Discord et tape `/`
pour voir apparaître `/start`, `/restart`, `/stop` et `/status`.

> Note : la synchronisation globale des slash commands peut prendre jusqu'à
> une heure pour apparaître partout la première fois. Pour un test immédiat en
> développement, tu peux synchroniser les commandes uniquement sur ta guilde de
> test (dis-le moi si tu veux que j'ajoute cette option).

## 3. Héberger le bot 24h/24 gratuitement

Le bot doit tourner en continu pour répondre aux commandes à tout moment. Voici
un tutoriel simple avec **Railway** (gratuit avec un crédit mensuel limité) —
Render et Koyeb fonctionnent sur le même principe.

### Option recommandée : Railway

1. Pousse ce projet sur GitHub (voir section suivante) — c'est déjà fait pour
   toi si tu as suivi ce guide jusqu'au bout.
2. Va sur https://railway.app et connecte-toi avec ton compte GitHub.
3. **New Project > Deploy from GitHub repo** > sélectionne
   `Awakening-Bots-Minecraft-`.
4. Railway détecte un projet Python (via `requirements.txt`) et lit la
   commande de démarrage directement dans le [`Procfile`](./Procfile) inclus
   (`worker: python main.py`) — rien à configurer manuellement.
5. Dans l'onglet **Variables**, ajoute tes variables d'environnement (les
   mêmes que dans `.env`) :
   - `DISCORD_TOKEN`
   - `MINESTRATOR_API_KEY`
   - `SERVER_ID`
   - `ANNOUNCE_CHANNEL_ID` (et `STATS_CHANNEL_ID` si différent)
6. Déploie. Railway relance automatiquement le bot s'il crashe et le fait
   tourner en continu tant que ton crédit gratuit n'est pas épuisé.

### Alternatives

- **Render** : créer un "Background Worker" (pas un "Web Service", car ce bot
  n'écoute pas de port HTTP), même logique de variables d'environnement.
- **Koyeb** : créer un service depuis le repo GitHub, type "Worker", même
  configuration de variables d'environnement.

## 4. Redémarrage automatique périodique

> Désactivé tant que `POWER_ACTIONS_ENABLED` vaut `false` (cas de l'offre
> gratuite, voir l'encadré en haut de ce README).

Le serveur redémarre automatiquement toutes les `RESTART_INTERVAL_HOURS`
heures (4h par défaut), même si des joueurs sont connectés :

1. Le bot vérifie combien de joueurs sont actuellement connectés.
2. Il envoie un message dans le salon `ANNOUNCE_CHANNEL_ID` annonçant le
   redémarrage dans `RESTART_WARNING_SECONDS` secondes (30s par défaut), avec
   la liste des joueurs connectés.
3. Il lance le redémarrage (`poweraction: restart10`, qui diffuse aussi un
   compte à rebours de 10s dans la console/le jeu).
4. Il surveille le retour en ligne du serveur ; si celui-ci ne redémarre pas
   tout seul, un message invite les joueurs à retaper `/start`.

En complément, une veille indépendante vérifie le statut toutes les
`STATUS_POLL_INTERVAL_SECONDS` secondes (2 min par défaut) : si le serveur
passe hors ligne en dehors de ce cycle (crash, arrêt manuel, etc.), un message
est envoyé dans le salon pour inviter les joueurs à retaper `/start`.

Ces deux tâches ne démarrent que si `ANNOUNCE_CHANNEL_ID` est renseigné dans
`.env` — récupère l'ID du salon en activant le mode développeur Discord
(Réglages utilisateur > Avancés > Mode développeur), puis clic droit sur le
salon > "Copier l'identifiant".

## 5. Panneau de statistiques en direct

Si `STATS_CHANNEL_ID` (ou à défaut `ANNOUNCE_CHANNEL_ID`) est renseigné, le
bot poste un message (embed) dans ce salon et le **met à jour sur place**
toutes les `STATS_UPDATE_INTERVAL_SECONDS` secondes (1 min par défaut) — pas
de spam de nouveaux messages, un seul qui s'actualise. Il affiche :

- l'état du serveur (en ligne / hors ligne / démarrage / arrêt)
- l'utilisation CPU, mémoire et disque (`GET /server/{id_server}/live`)
- les joueurs connectés (nombre + pseudos)
- l'uptime, quand le serveur est en ligne

Aucun log de la console n'est affiché — uniquement les métriques de
performance, comme demandé. Le bot retrouve automatiquement son propre
message au redémarrage (il cherche dans les 20 derniers messages du salon) au
lieu d'en recréer un nouveau à chaque fois.

## 6. Dépôt Git et GitHub

Le dépôt local a été initialisé et lié au dépôt distant
`https://github.com/Matt0967/Awakening-Bots-Minecraft-.git`. Les secrets
(`.env`) sont exclus via `.gitignore` et ne seront jamais poussés sur GitHub.

## Permissions Discord nécessaires

Lors de l'invitation du bot (OAuth2 URL Generator), coche uniquement :

- **Scopes** : `bot`, `applications.commands`
- **Permissions du bot** :
  - `Send Messages` (répondre dans les salons)
  - `Use Slash Commands` (généralement inclus automatiquement avec le scope
    `applications.commands`)
  - `Embed Links` (nécessaire pour le panneau de statistiques)
  - `Read Message History` (le bot relit le salon de statistiques au
    redémarrage pour retrouver et mettre à jour son propre message)

Aucune permission d'administration n'est nécessaire — le bot n'a besoin
d'aucun accès aux salons vocaux, à la modération, ou à la gestion du serveur
Discord. Toute la logique de démarrage/arrêt passe par l'API Minestrator, pas
par Discord.

`/start`, `/restart` et `/status` sont utilisables par **tout membre du
serveur Discord**, sans configuration particulière. Seul `/stop` est
restreint : par défaut, réservé aux membres ayant la permission Discord native
**"Gérer le serveur"** ; tu peux le restreindre à un rôle précis à la place en
définissant `ADMIN_ROLE_NAME` dans `.env`.
