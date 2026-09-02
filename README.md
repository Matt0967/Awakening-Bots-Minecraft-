# Sengoku SMP — Bot Discord de contrôle serveur (Minestrator)

Bot Discord permettant à tes joueurs de démarrer le serveur Minecraft Sengoku SMP
(hébergé sur Minestrator) via une simple commande `/start`, sans leur donner accès
au panel d'administration.

## Commandes

- `/start` — démarre le serveur via l'API Minestrator (`PATCH /mybox/{id_mybox}/server/enable`).
- `/stop` — arrête le serveur, réservé aux admins (`PATCH .../server/disable`).
- `/status` — affiche l'état actuel du serveur et les joueurs connectés (`GET /server/{id_server}/live`).

Le bot fait aussi tourner deux tâches de fond (voir section "Redémarrage
automatique" plus bas) : un redémarrage périodique toutes les 4h, et une
alerte dans le salon Discord si le serveur tombe hors ligne de façon
inattendue.

La documentation officielle de l'API (spec OpenAPI) est incluse dans ce dépôt :
[`minestrator-api-fr.yaml`](./minestrator-api-fr.yaml). C'est la source de
vérité si Minestrator fait évoluer son API — `main.py` s'appuie exactement
dessus (endpoints, headers, schémas de réponse/erreur).

## 1. Récupérer ta clé API, ton ID de MyBox et ton ID de serveur sur Minestrator

1. Connecte-toi sur https://minestrator.com puis va dans
   **Compte → Clés API** (directement : https://minestrator.com/my/account?section=api).
2. Génère une clé API et **copie-la immédiatement** — elle est affichée **déjà
   encodée** : colle-la telle quelle dans `.env`, ne la ré-encode pas. Garde-la
   secrète, elle donne un accès équivalent à ton mot de passe pour les actions
   autorisées.
3. **Important (offre gratuite)** : l'API Minestrator précise qu'elle est
   "accessible à tous les clients Minestrator.com", donc a priori disponible
   même sur l'offre gratuite. Un usage abusif (polling trop fréquent, etc.)
   peut cependant faire désactiver l'accès API — reste dans les intervalles
   par défaut du bot (`RESTART_INTERVAL_HOURS`, `STATUS_POLL_INTERVAL_SECONDS`)
   sauf besoin réel.
4. Récupère ton **`MYBOX_ID`** : dans le panel, sur la page de ta MyBox, l'ID
   apparaît dans l'URL (ex: `.../mybox/12345/...`).
5. Récupère ton **`SERVER_ID`** : sur la page de ton serveur Minecraft dans
   cette MyBox, l'ID apparaît dans l'URL (ex: `.../server/67890/...`).

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

```bash
cp .env.example .env
```

Ouvre `.env` et remplis `DISCORD_TOKEN`, `MINESTRATOR_API_KEY` et `SERVER_ID`.
Ce fichier `.env` est ignoré par Git (voir `.gitignore`) — il ne sera jamais
envoyé sur GitHub.

### Lancer le bot

```bash
python main.py
```

Si tout fonctionne, tu verras dans le terminal `Connecté en tant que ...` puis
`X commande(s) slash synchronisée(s).`. Va sur ton serveur Discord et tape `/`
pour voir apparaître `/start` et `/status`.

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
4. Railway détecte un projet Python. Dans les **Settings** du service, définis
   la commande de démarrage : `python main.py`.
5. Dans l'onglet **Variables**, ajoute tes variables d'environnement (les
   mêmes que dans `.env`) :
   - `DISCORD_TOKEN`
   - `MINESTRATOR_API_KEY`
   - `SERVER_ID`
6. Déploie. Railway relance automatiquement le bot s'il crashe et le fait
   tourner en continu tant que ton crédit gratuit n'est pas épuisé.

### Alternatives

- **Render** : créer un "Background Worker" (pas un "Web Service", car ce bot
  n'écoute pas de port HTTP), même logique de variables d'environnement.
- **Koyeb** : créer un service depuis le repo GitHub, type "Worker", même
  configuration de variables d'environnement.

## 4. Redémarrage automatique périodique

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

## 5. Dépôt Git et GitHub

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
  - `Embed Links` (optionnel, si tu veux enrichir les réponses plus tard)

Aucune permission d'administration n'est nécessaire — le bot n'a besoin
d'aucun accès aux salons vocaux, à la modération, ou à la gestion du serveur
Discord. Toute la logique de démarrage/arrêt passe par l'API Minestrator, pas
par Discord.

Si tu utilises `ALLOWED_ROLE_NAME` (pour `/start`) ou `ADMIN_ROLE_NAME` (pour
`/stop`) pour restreindre l'usage à un rôle spécifique, aucune permission
Discord supplémentaire n'est requise : la vérification se fait directement
dans le code du bot. Par défaut (sans `ADMIN_ROLE_NAME`), `/stop` est réservé
aux membres ayant la permission Discord native **"Gérer le serveur"**.
