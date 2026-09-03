# Message pour le support Minestrator

**Objet :** API — 403 API_FORBIDDEN sur PUT /server/{id_server}/poweraction sans en-tête Origin

---

Bonjour,

Je rencontre un comportement qui semble être un bug sur l'API REST, et j'ai
isolé la cause précise avec une série de tests.

**Contexte**

- MyBox : Will of Audacity (code support #FREE2XOY1)
- Serveur : Shogunat_SMP (code support #FREEEOTOJ), `id_server` 488332
- J'utilise une clé API générée depuis Compte → Clés API, pour piloter mon
  serveur depuis un bot Discord (usage externe, tel que décrit dans votre
  documentation).

**Le problème**

Les requêtes de lecture fonctionnent parfaitement, mais toutes les requêtes qui
modifient l'état renvoient `403 API_FORBIDDEN` — sauf si j'ajoute un en-tête
`Origin` ou `Referer` pointant vers `minestrator.com`.

Tests réalisés avec **la même clé API, le même serveur et le même endpoint** :

| Requête | Résultat |
|---|---|
| `GET /server/488332/live` (aucun en-tête particulier) | 200 OK |
| `PUT /server/488332/poweraction` sans `Origin` ni `Referer` | 403 `API_FORBIDDEN` |
| `PUT /server/488332/poweraction` avec un `User-Agent` de navigateur seul | 403 `API_FORBIDDEN` |
| `PUT /server/488332/poweraction` avec `Origin: https://minestrator.com` | 200 OK |
| `PUT /server/488332/poweraction` avec `Referer: https://minestrator.com/` | 200 OK |
| `PUT /server/488332/poweraction` avec `Origin: https://example.com` | 403 `API_FORBIDDEN` |

Corps de requête utilisé dans tous les cas : `{"poweraction": "start"}`
En-tête d'authentification : `Authorization: Bearer <ma clé API>`

**Pourquoi cela ressemble à un bug**

L'en-tête `Origin` est un mécanisme de protection anti-CSRF appliqué par les
navigateurs. Il n'a pas d'objet pour une authentification par token `Bearer` :
un appel serveur-à-serveur (script, bot, intégration) n'envoie pas d'`Origin`,
et ne peut pas être victime d'une attaque CSRF puisqu'il n'y a pas de cookie de
session impliqué.

Concrètement, cette vérification bloque tous les usages externes légitimes de
l'API pour les actions d'alimentation, alors que votre documentation indique
explicitement que « l'API est accessible à tous les clients MineStrator.com »
et prévoit « l'utilisation depuis une application externe ». Le testeur intégré
à votre documentation, lui, fonctionne toujours — car le navigateur ajoute
automatiquement l'en-tête `Origin`, ce qui masque le problème lors des tests
depuis la doc.

**Ma question**

S'agit-il bien d'un comportement involontaire ? Si oui, serait-il possible de
ne pas exiger `Origin`/`Referer` sur les requêtes authentifiées par clé API ?

Si au contraire c'est une restriction volontaire, pourriez-vous me le confirmer
et l'indiquer dans la documentation ? Cela éviterait à d'autres clients de
passer du temps à chercher l'origine de ces 403.

En attendant votre retour, j'ajoute l'en-tête `Origin` dans mon client pour
pouvoir avancer — mais je préfère vous le signaler, car si la configuration est
corrigée, cette solution de contournement n'aura plus lieu d'être.

Merci d'avance pour votre retour,

Cordialement,
