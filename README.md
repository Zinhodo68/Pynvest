
## 🗄️ Schéma de base de données

### Modèles SQLAlchemy (`database/models.py`)

**Membre, Portefeuille, Position, Valorisation, CoursHistorique** — inchangés vs versions précédentes.

#### Transaction (champs enrichis)

Champs existants : `id`, `portefeuille_id`, `date_operation`, `type_operation`, `montant`, `libelle`, `parent_transaction_id`

Champs pour traçabilité des opérations de titre ou de flux complexes :
- `ticker` : ticker Yahoo (ex: 'MC.PA')
- `code` : ISIN (pour OPCVM)
- `nom_titre` : nom du titre (snapshot de l'actif concerné par l'opération)
- `categorie` : catégorie (snapshot)
- `quantite` : quantité de titres ou de parts impliquées
- `prix_unitaire` : prix unitaire au moment de l'opération

Tous les champs liés aux titres sont nullable. Ils sont remplis si `type_operation` est `'achat'`, `'vente'`, `'dividende'` (réinvesti), ou `'frais'` (en parts).

## 🏗️ Architecture clé : Position vs Transaction

**Décision architecturale (Session 2)** : approche C+ hybride

| Concept | Source de vérité | Usage |
|---------|------------------|-------|
| État actuel (quantités, PRU, valeur du jour) | `Position` | Affichage des cartes, tableaux, KPIs |
| Historique (qui détenait quoi à quelle date) | `Transaction` | Backfill, graphique d'évolution |

**Avantage** : pas de calcul lourd à chaque affichage, mais reconstruction historique exacte possible.

## 🔁 Logique des arbitrages internes (Session 4)

**Concept clé** : un arbitrage est représenté par **2 transactions liées** par `parent_transaction_id`.

### Cas 1 : Arbitrage Fonds € → Titre (achat)
- **Tx parent** : `type='achat'`, `parent_id=NULL` → l'achat du titre
- **Tx enfant** : `type='vente'`, `parent_id=<tx parent>` → vente du Fonds €

### Cas 2 : Arbitrage Titre → Fonds € (vente)
- **Tx parent** : `type='vente'`, `parent_id=NULL` → vente du titre
- **Tx enfant** : `type='versement'`, `parent_id=<tx parent>` → versement vers Fonds €

### Règles de calcul

**Capital investi** (`Portefeuille.total_verse`) :
- ✅ Compte uniquement les flux **externes** (`parent_transaction_id IS NULL`)
- ❌ Ignore les arbitrages internes

**Backfill du cash** (`backfill_valorisations`) :
- Une transaction est "interne" si elle est **parent d'arbitrage** (a un enfant) **OU enfant d'arbitrage**
- Pour les transactions internes : **NE PAS toucher au cash**, seules les positions évoluent

## ⚙️ Fonctionnement des composants clés

### 🔄 Mise à jour des cours (`services/quotes_updater.py`)
*[Inchangé]*

### 🏗️ Backfill (`services/backfill.py`)

**`backfill_cours_historique(portefeuille_id)`**
- Source = transactions d'achat/vente (pas seulement positions actuelles)
- Permet de récupérer l'historique même pour des titres déjà revendus
- Pour chaque ticker Yahoo unique → téléchargement complet via `yfinance.history()`
- Insertion dans `CoursHistorique` (sans doublons)

**`backfill_valorisations(portefeuille_id)`**
- ⚠️ Supprime toutes les valorisations existantes
- Date de départ = première transaction
- **Précalcul** des `parent_ids_with_child` pour identifier les parents d'arbitrage
- Pour chaque jour :
  - Rejoue toutes les transactions jusqu'à ce jour
  - **Ignore l'impact cash pour les transactions internes** (parent ou enfant d'arbitrage)
  - Maintient un dict `positions_held : {ticker/code/nom: {quantité, PRU, ...}}`
  - Calcule `valo_titres = Σ quantité × cours_du_jour`
  - Calcule `valo_totale = cash + valo_titres`
  - Crée un snapshot `Valorisation`

**Avantage** : historique exact même avec achats/ventes successifs et arbitrages internes.

### 📈 Graphique d'évolution (`pages/portefeuille_detail/_chart.py`)

- Format ECharts en mode `category` (jamais `time`)
- 3 séries : Valorisation, Capital investi, +/- value
- **Capital investi** filtré : exclut les transactions avec `parent_transaction_id` non nul

### 🛒 Dialog d'achat (`pages/portefeuille_detail/_buy_dialog.py`)

- 3 modes : ACTION/ETF/CRYPTO, OPCVM/SICAV, MANUEL
- PRU auto-rempli selon la date d'achat (Yahoo)
- Logique AV/PER : l'achat utilise un Fonds € source existant (arbitrage)
- Impossible de créer un Fonds € via ce dialogue
- Remplit les champs Transaction : `ticker`, `code`, `nom_titre`, `categorie`, `quantite`, `prix_unitaire`

### 💹 Dialog de vente (`pages/portefeuille_detail/_sell_dialog.py`)

- 🆕 **Liste filtrée** : exclut Cash, Fonds €, Fonds Euro (réserves de liquidités)
- Sur AV/PER : sélection obligatoire d'un Fonds € de destination
- PRU auto-rempli selon la date de vente (Yahoo)
- Détection automatique de la source (yahoo si ticker, boursorama si code, manual sinon)

### ➕ Dialogue de transaction générique (`pages/portefeuille_detail/_transactions.py`)

Gère les types : Versement, Retrait, Intérêts Fonds €, Dividende (D ou C), Frais (€ ou parts).

**🆕 Édition** : actuellement bloquée pour les achats/ventes (message clair invitant à supprimer/recréer).

**🆕 Suppression intelligente** :
- **Achat AV/PER** → restaure la quantité du Fonds € source, supprime la position du titre acheté, supprime les enfants
- **Vente AV/PER** → reprélève le Fonds € destination, restaure la position du titre vendu (création si vente totale)
- **Achat/Vente PEA/CTO** → ajuste le cash normalement
- **Dividende C / Frais en parts** → restaure les quantités sur la position source
- **Flux sur Fonds €** → ajuste la quantité du Fonds €
- **Flux cash** → ajuste le cash

### 📋 Liste des positions (`pages/portefeuille_detail/_positions.py`)

🆕 **Affichage trié** : titres en premier, **réserves de liquidités** (Cash, Fonds €) à la fin avec un séparateur visuel "💰 RÉSERVES DE LIQUIDITÉS".

## ✅ Fonctionnalités déjà développées

### 🟢 Stable et testé

- [x] Gestion des membres
- [x] Création de portefeuilles (multi/mono-support)
- [x] Ajout de positions (Action/ETF, OPCVM, manuel)
- [x] Récupération des cours actuels (Yahoo + Boursorama)
- [x] Historique des cours via yfinance
- [x] Reconstruction exacte de l'historique de valorisation depuis les transactions
- [x] Graphique d'évolution multi-courbes
- [x] Format intelligent des dates de l'axe X
- [x] Gestion correcte des achats/ventes successifs du même titre dans le graphique
- [x] PRU auto-rempli selon date d'achat (Yahoo)
- [x] PRU auto-rempli selon date de vente (Yahoo)
- [x] **Gestion correcte des arbitrages internes** (cash + KPI + graphique)
- [x] **Capital investi exact** (exclut les arbitrages internes)
- [x] Gestion des Fonds Euro :
  - [x] Fonds Euro non créables manuellement via le dialogue d'achat de titre
  - [x] Arbitrage AV/PER : l'achat de titres prélève un Fonds € existant
  - [x] Versement/Retrait sur un Fonds € spécifique (pour AV/PER)
  - [x] Saisie annuelle des intérêts des Fonds Euro
- [x] Gestion des Dividendes :
  - [x] Saisie du dividende distribué en cash (impacte Cash/Fonds €)
  - [x] Saisie du dividende réinvesti en parts (impacte la Position de l'actif)
  - [x] Double saisie (montant total / par part) pour les dividendes distribués
  - [x] Affichage clair "Dividende (D)" / "Dividende (C)" dans la liste
- [x] Gestion des Frais :
  - [x] Saisie des frais en euros (impacte Cash/Fonds €)
  - [x] Saisie des frais en parts (prélèvement de la Position d'un actif)
  - [x] Double saisie (quantité à prélever / quantité finale) pour les frais en parts
  - [x] Affichage clair "Frais (en parts)" dans la liste
- [x] **Liste de vente** : exclusion automatique des réserves (Cash, Fonds €)
- [x] **Tableau des positions** : titres puis réserves de liquidités (avec séparateur)
- [x] **Suppression de transaction intelligente** : restauration des positions sources, gestion des arbitrages enfants, jamais de Cash fantôme sur AV/PER

### 🟡 En cours / partiel

- [ ] Adaptation des dates au zoom dynamique du graphique

### 🔴 Limitations connues / Non développé

- ❌ **Édition directe des achats/ventes** non supportée. Pour modifier, supprimer la transaction et la recréer.
- ❌ **Édition des transactions de flux** (versement, retrait, dividendes, intérêts, frais) non supportée. Pour modifier, supprimer et recréer.
- ❌ **SCPI** non gérées correctement (système de revalorisation et distributions spécifiques).
- ❌ Pas de gestion des fractionnements d'actions.
- ❌ Pas d'authentification / multi-user.
- ❌ Pas de sauvegarde automatique de la BDD.
- ❌ Pas d'export PDF/Excel.
- ⚠️ **Incohérence catégories Fonds €** : certaines positions en BDD ont `'Fonds €'`, d'autres `'Fonds Euro'`. Le code accepte les deux orthographes via `Position.categorie.in_(['Fonds €', 'Fonds Euro'])`. À harmoniser un jour via un script de migration.

## 🎯 Roadmap Sessions

### ✅ Session 1 — Graphique d'évolution (terminée)

**Problèmes résolus** : crash threads, backfill bidon, `date_creation None`, valorisation incorrecte, cash non pris en compte, doublons d'années, PRU sans lien avec marché.

**Ajouts** : `get_yahoo_history()`, `get_yahoo_price_at_date()`, refonte backfill v1, format intelligent des dates, PRU auto à l'achat.

### ✅ Session 2 — Refonte historique (terminée)

**Problèmes résolus** : PRU auto à la vente (avec détection auto de la source), graphique cassé après vente.

**Ajouts** : 6 nouveaux champs dans Transaction, migration BDD via `migrate.py`, `reset_data.py`, `_buy_dialog.py` et `_sell_dialog.py` enrichis, `backfill.py` complètement refondu.

**Décisions architecturales** : Approche C+ hybride, modèle Transaction étendu mais nullable.

### ✅ Session 3 — Fonds €, Dividendes et Frais (terminée)

**Problèmes résolus** :
- Gestion des Fonds Euro : Arbitrage AV/PER (achat de titres depuis Fonds €), versements/retraits sur Fonds €, impossibilité de créer manuellement un Fonds € via "Acheter un titre"
- Saisie des intérêts annuels des Fonds Euro
- Gestion complète des Dividendes : distribués en cash (D) ou réinvestis en parts (C), double saisie montant total/par part
- Gestion des Frais : en euros (débit Cash/Fonds €) ou en parts d'actifs (débit Position d'un titre), double saisie quantité à prélever/quantité finale
- Affichage clair des types de dividendes (D/C) et des frais en parts dans la liste des transactions

**Ajouts** : Logiques complexes dans `_transactions.py` et `_buy_dialog.py`, améliorations des validations et de la traçabilité.

### ✅ Session 4 — Cohérence des arbitrages & UX (terminée)

**Problèmes résolus** :
- 🐛 **Capital investi gonflé par les arbitrages internes** (graphique + KPI) : le total versé comptait à tort les `versement` enfants d'arbitrage
- 🐛 **Valorisation gonflée par double-comptage du cash** lors des arbitrages : le cash était à la fois crédité par la vente parente ET la position Fonds € augmentée par le versement enfant
- 🐛 **Suppression d'achat sur AV/PER** créait à tort une position "Cash" fantôme au lieu de réinjecter dans le Fonds €
- 🐛 **Édition d'achat/vente** ouvrait un formulaire vide non éditable

**Ajouts** :
- Filtrage `parent_transaction_id IS NULL` dans `_chart.py` et `Portefeuille.total_verse`
- Précalcul `parent_ids_with_child` dans `backfill_valorisations` pour identifier les arbitrages parents
- Refonte de `_confirm_delete_transaction` avec 6 cas distincts (achat, vente, dividende C, frais en parts, flux Fonds €, flux cash)
- Filtrage des réserves (Cash, Fonds €, Fonds Euro) dans la liste des positions vendables
- Tri visuel dans `_positions.py` : titres puis réserves avec séparateur
- Blocage propre de l'édition achat/vente avec message invitant à supprimer/recréer

### 🔜 Session 5 — Polish UI

- Zoom dynamique du graphique
- Indicateur de loading pendant backfill
- Supprimer les points sur les courbes
- Améliorations diverses

### 🔜 Plus tard

- Édition véritable des achats/ventes (extension de `_buy_dialog` et `_sell_dialog`)
- Édition des transactions de flux
- Harmonisation des catégories `'Fonds €'` / `'Fonds Euro'` (script de migration)
- Export PDF/Excel
- SCPI (système de revalorisation et distributions)
- Splits/fractionnements
- Authentification
- Indicateurs avancés (TRI, volatilité, max drawdown)
- Comparaison vs benchmark

## 🐛 Pièges connus / Anti-patterns à éviter

❌ **Ne JAMAIS utiliser `threading.Thread` avec NiceGUI**
- Crash : `RuntimeError: The current slot cannot be determined`
- ✅ Utiliser `await run.io_bound(...)` ou `asyncio.to_thread(...)`

❌ **ECharts.xAxis.type = 'time' avec strings ISO**
- Affiche des `01:00:01` partout
- ✅ Utiliser `'category'` avec format manuel

❌ **Les events `update:model-value` sur `ui.input` ne se déclenchent pas avec `bind_value`**
- ✅ Écouter directement le composant source (ex: `ui.date`)
- ✅ Ou utiliser `'blur'` sur l'input

❌ **`Portefeuille.date_creation = None` casse silencieusement le backfill**
- ✅ Le backfill utilise désormais la date de la première transaction

❌ **Calculer l'historique uniquement depuis les positions actuelles**
- Si un titre a été vendu, la position n'existe plus → historique cassé
- ✅ Source = transactions (qui contiennent les nouveaux champs `ticker/quantite/prix`)

❌ **Sommer naïvement tous les `versement` pour calculer le capital investi**
- Les arbitrages internes (vente titre → versement Fonds €) sont représentés comme des `versement` mais ne sont **PAS** des apports externes
- ✅ Filtrer sur `parent_transaction_id IS NULL` partout (chart, KPI, models)

❌ **Créer une ligne "Cash" sur AV/PER lors d'opérations**
- En AV/PER, il n'y a pas de cash : tout passe par les Fonds €
- ✅ Toujours router vers le Fonds € approprié sur ces types de portefeuille

❌ **Supprimer une transaction parente d'arbitrage sans gérer les enfants**
- Les enfants restent en BDD avec leur impact non annulé → BDD incohérente
- ✅ Boucler sur `t.children` et annuler chaque impact (Fonds €, position, cash) avant suppression