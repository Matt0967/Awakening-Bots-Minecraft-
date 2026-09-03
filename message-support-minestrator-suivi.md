# Message de suivi pour le support Minestrator

**Objet :** Suite au ticket API/`Origin` — pérennité du contournement et validation d'un usage externe

---

Bonjour Tom,

Merci pour votre réponse et pour la mise à jour de la documentation.

Maintenant que je sais que la restriction est volontaire, j'aimerais sécuriser
mon usage sur le long terme. Je me permets donc trois questions.

**1. Le contournement par en-tête `Origin` est-il pérenne ?**

Mon bot envoie aujourd'hui `Origin: https://minestrator.com` sur les requêtes
`PUT /server/{id_server}/poweraction`, ce qui fonctionne parfaitement. Mais comme
il s'agit d'une restriction volontaire, je préfère demander plutôt que de
supposer : est-ce un comportement sur lequel je peux m'appuyer durablement, ou
risque-t-il d'être durci (vérification renforcée, liste d'origines autorisées,
etc.) ?

Si un changement de ce type est prévu, même sans date, un simple « oui, c'est
susceptible d'évoluer » me suffirait : je préviendrais mes joueurs et
j'anticiperais une solution de repli. Et s'il existe une manière **recommandée**
d'appeler l'API depuis une application externe (un en-tête dédié, un type de clé
particulier), je bascule dessus volontiers — je préfère la méthode officielle au
contournement.

**2. Mon cas d'usage est-il conforme à vos conditions ?**

Je souhaite être totalement transparent sur ce que fait le bot, pour être sûr de
ne pas me retrouver avec un accès API désactivé sans le vouloir.

- Serveur : Shogunat_SMP (code support #FREEEOTOJ), `id_server` 488332,
  sur la MyBox Will of Audacity (#FREE2XOY1) — offre gratuite.
- Le bot est un bot Discord hébergé en ligne, qui utilise **ma** clé API
  personnelle. Personne d'autre n'a accès à la clé ni au panel.
- Les membres de mon Discord peuvent lancer les commandes `/start` et `/restart`
  sans être administrateurs. C'est tout l'intérêt : les joueurs n'ont plus besoin
  d'attendre que je sois connecté pour que le serveur démarre, et ils n'ont
  jamais accès au panel d'administration.
- Volume d'appels : un `GET /server/{id_server}/live` toutes les 2 minutes pour
  la surveillance, un autre toutes les 60 secondes pour un panneau de
  statistiques, et un `poweraction` uniquement lors d'une action explicite d'un
  joueur ou du redémarrage automatique (toutes les 4 heures). Ces intervalles
  sont configurables : si ce rythme vous paraît trop élevé, dites-moi la
  fréquence que vous jugez acceptable et je l'ajuste immédiatement.

Est-ce que cet usage vous convient tel quel ? Si une limite existe (nombre
d'appels par minute, par jour…), je serais preneur du chiffre exact pour m'y
conformer.

**3. Une validation de votre côté serait-elle envisageable ?**

Le bot est développé en Python, il est open source, et il s'appuie strictement
sur votre spécification OpenAPI officielle (aucun appel non documenté, aucun
scraping du panel).

Si cela vous intéresse, je peux vous communiquer le dépôt afin que votre équipe
technique y jette un œil. Et si vous jugez le projet propre, seriez-vous ouverts
à le mentionner ou le référencer d'une façon ou d'une autre (documentation,
communauté, tutoriel) ? Beaucoup de vos clients cherchent exactement cela :
permettre à leurs joueurs de démarrer le serveur sans partager les accès au panel.

Ce n'est évidemment pas une demande prioritaire — le point important pour moi
reste les questions 1 et 2.

Merci d'avance pour votre retour,

Cordialement,
