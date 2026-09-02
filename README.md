# Sengoku SMP — Bot Discord de contrôle serveur (Minestrator)

Bot Discord permettant à tes joueurs de démarrer le serveur Minecraft Sengoku SMP
(hébergé sur Minestrator) via une simple commande `/start`, sans leur donner accès
au panel d'administration.

## Commandes

- `/start` — démarre le serveur via l'API Minestrator (POST).
- `/status` — affiche l'état actuel du serveur : en ligne / hors ligne / en démarrage (GET).

## 1. Récupérer ta clé API et ton ID de serveur sur Minestrator

⚠️ Minestrator ne publie pas de documentation API publique stable — les étapes
ci-dessous sont les plus probables mais peuvent varier légèrement selon les
mises à jour du panel. Si tu ne trouves pas ces options, ouvre un ticket au
support Minestrator en demandant explicitement : "accès API pour piloter mon
serveur par une application externe".

1. Connecte-toi à ton panel Minestrator (https://panel.minestrator.com ou l'URL
   fournie par ton offre).
2. Repère ton **ID de serveur** : il apparaît généralement dans l'URL de la page
   de gestion de ton serveur (ex: `.../server/<SERVER_ID>/...`) ou dans les
   informations générales du serveur.
3. Cherche une section **"API"**, **"Développeur"** ou **"Intégrations"** dans
   les paramètres de ton compte ou du serveur. C'est là que tu génères une clé
   API (parfois appelée "token API" ou "clé personnelle").
4. **Copie cette clé immédiatement** (elle n'est souvent affichée qu'une fois)
   et garde-la secrète — elle donne un accès équivalent à ton mot de passe pour
   les actions autorisées.
5. **Important (offre gratuite)** : vérifie que ton offre gratuite inclut bien
   l'accès à l'API. Certains hébergeurs réservent cette fonctionnalité aux
   offres payantes. Si l'option "API" n'apparaît pas dans ton panel, contacte
   le support pour confirmer.
6. Une fois la clé et l'ID en main, vérifie aussi le **chemin exact des
   endpoints** (démarrer un serveur, lire son statut) et le **header
   d'authentification attendu** (`Authorization: Bearer ...`, `X-Api-Key`,
   etc.) — au besoin en inspectant les requêtes réseau du panel (F12 >
   Réseau > clique sur "Démarrer" dans l'interface) ou en demandant au support.
   Le fichier `main.py` regroupe ces valeurs en haut de fichier
   (`MINESTRATOR_API_BASE_URL`, `START_ENDPOINT`, `STATUS_ENDPOINT`,
   `_headers()`) pour que tu puisses les ajuster facilement sans toucher au
   reste du code.

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

## 4. Dépôt Git et GitHub

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

Si tu utilises `ALLOWED_ROLE_NAME` pour restreindre l'usage à un rôle
spécifique, aucune permission Discord supplémentaire n'est requise : la
vérification se fait directement dans le code du bot.
