📊 PYNVEST — Documentation projet pour reprise rapide
Document de contexte pour Claude (ou autre IA) — permet une mise à jour rapide de la compréhension du projet en début de session.

🔗 Liens & Accès
GitHub (public) : https://github.com/Zinhodo68/Pynvest
Propriétaire : Zinhodo68
Stack : Python 3.14 + NiceGUI + SQLAlchemy + SQLite + ECharts
IDE utilisé : PyCharm sous Windows
Environnement : .venv dans C:\Users\liogi\PycharmProjects\Projects.venv

🎯 Objectif du projet
Pynvest est une webapp personnelle de gestion du patrimoine financier familial. Elle permet de :
- Gérer plusieurs membres de la famille
- Créer différents types de portefeuilles (PEA, AV, livrets, comptes-titres, PER...)
- Suivre les positions (actions, ETF, OPCVM, SCPI, crypto, fonds €, cash)
- Visualiser l'évolution du patrimoine dans le temps
- Récupérer automatiquement les cours via Yahoo Finance et Boursorama
- Consulter des relevés annuels (situation au 31/12 de chaque année)

Usage local privé (pas multi-utilisateur, pas d'authentification pour le moment).

📁 Structure du projet
Pynvest/
├── main.py                     # Point d'entrée NiceGUI
├── migrate.py                  # Script de migration BDD
├── reset_data.py               # Script de reset des données (préserve les Fonds €)
├── database/
│   ├── db.py                   # 🔄 Connexion SQLAlchemy + WAL + timeout (mode robuste)
│   └── models.py               # ORM (Membre, Portefeuille, Position, Transaction, Valorisation, CoursHistorique)
├── services/
│   ├── _boursorama.py          # Scraper cours OPCVM/SICAV (cours du jour uniquement)
│   ├── _yahoo.py               # 🔄 API yfinance (cours actuel + historique avec filtrage NaN)
│   ├── _state.py               # État applicatif (last_update_date)
│   ├── market_data.py          # Façade unifiée multi-sources
│   ├── quotes_updater.py       # MAJ des cours + déclenchement backfill
│   ├── backfill.py             # 🔄 Reconstruction depuis transactions (filtrage tickers + commit incrémental)
│   ├── search.py               # Recherche unifiée (DB + Yahoo + Boursorama)
│   └── positions_data.py       # Helpers pour les positions
├── pages/
│   ├── dashboard/
│   ├── membres/
│   ├── portefeuilles/
│   ├── portefeuilles_data.py
│   ├── positions_data.py
│   └── portefeuille_detail/
│       ├── __init__.py         # Redirige vers _content.py
│       ├── _content.py         # Orchestrateur principal
│       ├── _header.py          # En-tête + bouton MAJ cours
│       ├── _stats.py           # Cartes KPI
│       ├── _chart.py           # Graphique ECharts d'évolution
│       ├── _positions.py       # 🔄 Tableau des positions + menu "Relevé annuel"
│       ├── _transactions.py    # 🔄 Dialogue transactions + backfill auto + helper anti-lock
│       ├── _buy_dialog.py      # 🔄 Achat avec recherche unifiée + fractions partout + backfill auto
│       ├── _sell_dialog.py     # 🔄 Vente avec fractions partout + backfill auto
│       ├── _releve_annuel.py   # 🆕 Popup relevé d'information annuel (situation au 31/12)
│       ├── _mono_support.py    # Vue spécifique livrets
│       └── _cash_helpers.py    # Helpers gestion du cash (impact_cash, ajuster_cash)
├── components/                 # Composants UI réutilisables
├── theme/                      # Thème sombre/clair
├── utils/
│   └── formatters.py           # format_money, format_percent, get_perf_color
└── uploads/                    # Logos uploadés

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

### Configuration SQLite robuste (Session 6)

`database/db.py` active automatiquement à chaque connexion :
- **WAL** (Write-Ahead Logging) → lectures concurrentes pendant écritures
- **busy_timeout=30000** → 30s d'attente avant erreur "database is locked"
- **synchronous=NORMAL** → bon compromis perf/sécurité
- **foreign_keys=ON** → contrôle d'intégrité référentielle

⚠️ Génère 2 fichiers à côté de `patrimoine.db` : `patrimoine.db-wal` et `patrimoine.db-shm` (à ajouter au `.gitignore`).

## 🏗️ Architecture clé : Position vs Transaction

**Décision architecturale (Session 2)** : approche C+ hybride

| Concept | Source de vérité | Usage |
|---------|------------------|-------|
| État actuel (quantités, PRU, valeur du jour) | `Position` | Affichage des cartes, tableaux, KPIs |
| Historique (qui détenait quoi à quelle date) | `Transaction` | Backfill, graphique d'évolution, relevés annuels |

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

## 🔍 Recherche unifiée (Session 5)

**Concept** : un **seul champ de recherche** dans le dialogue d'achat qui interroge **3 sources en parallèle** + propose la création manuelle.

### Architecture (`services/search.py`)

**`unified_search(query, limit_per_source=6)`** — orchestrateur asynchrone qui :
1. **Détecte les ISIN** (regex `^[A-Z]{2}[A-Z0-9]{9}\d$`) → priorise Boursorama
2. Lance en parallèle (`asyncio.gather`) :
   - `search_in_db(query)` — titres déjà manipulés via `Transaction.distinct()`
   - `search_yahoo(query)` — actions, ETF, crypto, indices
   - `search_opcvm(query)` — OPCVM/SICAV via Boursorama
3. Retourne un dict groupé : `{'db': [...], 'yahoo': [...], 'boursorama': [...], 'is_isin': bool}`

**`search_in_db(query)`** — recherche dans les transactions passées :
- Source : `SELECT DISTINCT ticker, code, nom_titre, categorie FROM transactions WHERE nom_titre IS NOT NULL`
- Filtrage Python case-insensitive sur ticker/code/nom
- **Exclut** les Cash et Fonds € (catégories `'Cash'`, `'Fonds €'`, `'Fonds Euro'`)
- Enrichit chaque résultat avec la liste des portefeuilles où le titre est encore détenu (via `Position`)

### UX (`_buy_dialog.py`)

- **Champ unique** avec debounce 400ms
- **Indicateur "🔖 ISIN détecté"** qui apparaît dynamiquement
- **4 groupes de résultats** affichés sous le champ :
  1. **📁 DÉJÀ DANS VOS PORTEFEUILLES** (vert) — avec mention `Portefeuille (quantité)`
  2. **🌐 YAHOO FINANCE**
  3. **📊 BOURSORAMA**
  4. **➕ CRÉER UN NOUVEAU SUPPORT** (toujours présent, prérempli avec la query)
- Au clic → pré-remplissage automatique du formulaire d'achat (toute la logique downstream conservée : PRU auto, arbitrage Fonds €, etc.)

## 🆕 Relevé d'information annuel (Session 6)

**Concept** : reconstruction de la situation exacte du portefeuille à n'importe quelle date (typiquement au 31/12 de chaque année).

### Module (`pages/portefeuille_detail/_releve_annuel.py`)

**`get_situation_at_date(portefeuille_id, target_date)`** — rejoue toutes les transactions jusqu'à la date cible :
- Calcule les positions détenues (quantité, PRU)
- Récupère le cours historique de chaque titre à la date cible (forward-fill depuis `CoursHistorique`)
- Calcule la valorisation, le cash, le capital investi, la +/- value globale
- Trie : titres d'abord (par valo décroissante), réserves de liquidités à la fin
- Respecte la logique des arbitrages internes

**`get_available_years(portefeuille_id)`** — liste les années pour lesquelles un relevé peut être généré (de la 1ère transaction jusqu'à l'année en cours - 1).

**`show_releve_annuel(portefeuille_id, annee, c, is_dark)`** — popup affichant :
- En-tête : nom du portefeuille + date de situation
- KPIs : total versé, valorisation, +/- value (montant + %)
- Cash et valorisation des titres en sous-totaux
- Tableau détaillé des positions avec PRU, cours historique, valorisation, +/-value
- Séparateur visuel "RÉSERVES DE LIQUIDITÉS"

### UX dans `_positions.py`

Une icône **📄 (description)** à droite du header "Positions" ouvre un menu déroulant listant les années disponibles. Clic sur une année → popup du relevé.

## ⚙️ Fonctionnement des composants clés

### 🔄 Mise à jour des cours (`services/quotes_updater.py`)
*[Inchangé]*

### 🏗️ Backfill (`services/backfill.py`) — refondu Session 6

**`backfill_cours_historique(portefeuille_id)`**
- Source = transactions d'achat/vente (pas seulement positions actuelles)
- 🆕 **Filtrage des faux tickers** : exclut les ISIN purs (regex) et les noms d'OPCVM (espaces, trop longs)
- 🆕 **Filtrage des NaN/Inf** dans les données Yahoo (jours sans cotation)
- 🆕 **Commit incrémental ticker par ticker** → si un ticker plante, les autres sont sauvegardés
- Pour chaque ticker valide → téléchargement complet via `yfinance.history()`
- Insertion dans `CoursHistorique` (sans doublons, sans NaN)

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

**Backfill automatique** : déclenché après chaque achat, vente, et transaction touchant un ticker Yahoo (via helper `_trigger_backfill_if_needed` dans `_transactions.py`).

### 📈 Graphique d'évolution (`pages/portefeuille_detail/_chart.py`)

- Format ECharts en mode `category` (jamais `time`)
- 3 séries : Valorisation, Capital investi, +/- value
- **Capital investi** filtré : exclut les transactions avec `parent_transaction_id` non nul

### 🛒 Dialog d'achat (`pages/portefeuille_detail/_buy_dialog.py`)

🆕 **Refonte UX (Session 5)** : un seul champ de recherche unifié remplace les 3 anciens modes (Action/ETF, OPCVM, Manuel).

🆕 **Achats fractionnaires partout (Session 6)** : toutes les catégories acceptent désormais des quantités décimales (4 décimales, step 0.0001), y compris les actions. Permet d'acheter 3.15 parts d'un ETF/ETC mal classé par Yahoo en `EQUITY`.

🆕 **Cohérence des calculs (Session 6)** : `update_summary()` recalcule toujours `montant = quantité × prix` au lieu de lire le champ montant (évite les désynchronisations).

🆕 **Backfill automatique post-achat (Session 6)** : après `session.commit()`, déclenchement de `backfill_cours_historique` (si ticker Yahoo) + `backfill_valorisations`.

### 💹 Dialog de vente (`pages/portefeuille_detail/_sell_dialog.py`)

🆕 **Ventes fractionnaires partout (Session 6)** : alignement avec le dialogue d'achat.

🆕 **Cohérence des calculs (Session 6)** : même fix que pour l'achat.

🆕 **Backfill automatique post-vente (Session 6)**.

### ➕ Dialogue de transaction générique (`pages/portefeuille_detail/_transactions.py`)

Gère les types : Versement, Retrait, Intérêts Fonds €, Dividende (D ou C), Frais (€ ou parts).

🆕 **Helper anti-lock (Session 6)** : `_trigger_backfill_if_needed()` est appelé **hors** de tout `with get_session()` pour éviter les locks SQLite. La détection `has_ticker` se fait dans la session courante avant `commit()`.

🆕 **Backfill automatique** après création/suppression de toute transaction.

**Édition** : actuellement bloquée pour les achats/ventes (message clair invitant à supprimer/recréer).

**Suppression intelligente** :
- **Achat AV/PER** → restaure la quantité du Fonds € source, supprime la position du titre acheté, supprime les enfants
- **Vente AV/PER** → reprélève le Fonds € destination, restaure la position du titre vendu (création si vente totale)
- **Achat/Vente PEA/CTO** → ajuste le cash normalement
- **Dividende C / Frais en parts** → restaure les quantités sur la position source
- **Flux sur Fonds €** → ajuste la quantité du Fonds €
- **Flux cash** → ajuste le cash

### 📋 Liste des positions (`pages/portefeuille_detail/_positions.py`)

**Affichage trié** : titres en premier, **réserves de liquidités** (Cash, Fonds €) à la fin avec un séparateur visuel "💰 RÉSERVES DE LIQUIDITÉS".

🆕 **Menu "Relevé annuel" (Session 6)** : icône 📄 dans le header → menu déroulant avec les années disponibles → popup détaillé.

### 🧹 Reset des données (`reset_data.py`)

🆕 **Préservation des Fonds €** :
- Supprime toutes les transactions, valorisations, positions classiques
- 🛡️ **Conserve** les positions de catégorie `'Fonds €'` / `'Fonds Euro'` créées à la création des portefeuilles AV/PER
- Réinitialise leur quantité à 0 et leur PRU à 1.0

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
- [x] **Reset des données préservant les Fonds €** créés à la création du portefeuille
- [x] **Recherche unifiée à l'achat** : un seul champ qui interroge BDD + Yahoo + Boursorama avec affichage groupé et détection ISIN
- [x] 🆕 **Backfill automatique des cours après chaque achat/vente/dividende C** → courbe de valorisation toujours à jour
- [x] 🆕 **Filtrage robuste des données Yahoo** (NaN, ISIN purs, OPCVM mal nommés) → plus de crashs SQL
- [x] 🆕 **Mode SQLite WAL + timeout 30s** → plus de "database is locked"
- [x] 🆕 **Helper anti-lock** : pas de double session imbriquée dans les workflows transactions
- [x] 🆕 **Achats/ventes fractionnaires** sur toutes les catégories (4 décimales)
- [x] 🆕 **Cohérence des calculs montant = quantité × prix** dans les dialogues achat/vente
- [x] 🆕 **Relevé d'information annuel** : popup avec situation détaillée du portefeuille au 31/12 de toute année passée

### 🟡 En cours / partiel

- [ ] Adaptation des dates au zoom dynamique du graphique

### 🔴 Limitations connues / Non développé

- ❌ **Édition directe des achats/ventes** non supportée. Pour modifier, supprimer la transaction et la recréer.
- ❌ **Édition des transactions de flux** (versement, retrait, dividendes, intérêts, frais) non supportée. Pour modifier, supprimer et recréer.
- ❌ **SCPI** non gérées correctement (système de revalorisation et distributions spécifiques).
- ❌ Pas de gestion des fractionnements d'actions.
- ❌ Pas d'authentification / multi-user.
- ❌ Pas de sauvegarde automatique de la BDD.
- ❌ Pas d'export PDF/Excel (le relevé annuel est uniquement à l'écran).
- ⚠️ **Incohérence catégories Fonds €** : certaines positions en BDD ont `'Fonds €'`, d'autres `'Fonds Euro'`. Le code accepte les deux orthographes via `Position.categorie.in_(['Fonds €', 'Fonds Euro'])`. À harmoniser un jour via un script de migration.
- ⚠️ **Doublon de fonction** dans `services/_yahoo.py` : `get_yahoo_price_at_date` est définie 2 fois (la 2ème écrase la 1ère). À nettoyer.
- ⚠️ **Performance backfill** : sur des portefeuilles avec 100+ transactions sur 8 ans, `backfill_valorisations` peut prendre quelques secondes. Pas de loader visuel pour le moment.

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
- 🐛 **Capital investi gonflé par les arbitrages internes** (graphique + KPI)
- 🐛 **Valorisation gonflée par double-comptage du cash** lors des arbitrages
- 🐛 **Suppression d'achat sur AV/PER** créait à tort une position "Cash" fantôme
- 🐛 **Édition d'achat/vente** ouvrait un formulaire vide non éditable

**Ajouts** :
- Filtrage `parent_transaction_id IS NULL` dans `_chart.py` et `Portefeuille.total_verse`
- Précalcul `parent_ids_with_child` dans `backfill_valorisations`
- Refonte de `_confirm_delete_transaction` avec 6 cas distincts
- Filtrage des réserves dans la liste des positions vendables
- Tri visuel dans `_positions.py` : titres puis réserves avec séparateur
- Blocage propre de l'édition achat/vente
- Préservation des Fonds € lors d'un reset_data

### ✅ Session 5 — Recherche unifiée à l'achat (terminée)

**Objectif** : remplacer les 3 onglets (Yahoo / Boursorama / Manuel) par un **champ de recherche unique** interrogeant toutes les sources en parallèle + la BDD locale.

**Ajouts** :
- Module **`services/search.py`** : `is_isin()`, `search_in_db()`, `unified_search()`
- Refonte complète de **`_buy_dialog.py`** : champ unique, debounce 400ms, 4 groupes de résultats, détection ISIN

### ✅ Session 6 — Robustesse, fractions & relevés annuels (terminée)

**Objectif** : fiabiliser la chaîne backfill (cours Yahoo) + permettre les achats fractionnaires + ajouter les relevés annuels.

**Problèmes résolus** :
- 🐛 **Courbe de valorisation plate après les anciens achats** : le backfill des cours Yahoo n'était pas déclenché lors d'un achat → `backfill_valorisations` valorisait tout au PRU
- 🐛 **Crash SQL "NOT NULL constraint failed: cours"** : Yahoo retournait des valeurs NaN qui faisaient planter `backfill_cours_historique` → rollback total → 0 valorisations
- 🐛 **Crash SQL "Invalid ISIN number"** : les noms d'OPCVM (avec espaces, accents) et les ISIN purs étaient passés à `yfinance.history()` qui les rejetait
- 🐛 **`database is locked`** : double `with get_session()` imbriqué dans `_transactions.py` (détection `has_ticker` dans une 2ème session)
- 🐛 **Quantité forcée entière** sur les ETF mal classés par Yahoo en `EQUITY` (ex: XAD1.DE)
- 🐛 **Désynchronisation montant ≠ quantité × prix** dans le summary du dialogue d'achat (changement de prix sans retaper la quantité)
- 🐛 **Attribut `Portefeuille.nom` inexistant** dans le relevé annuel (le bon est `nom_affiche`)

**Ajouts** :
- 🆕 Helper `_trigger_backfill_if_needed(portefeuille_id, has_ticker)` dans `_transactions.py` → centralise le backfill, appelé hors session
- 🆕 Détection `has_ticker` faite **dans la session courante** avant `commit()` (puis appel backfill hors session)
- 🆕 Backfill automatique post-achat (`_buy_dialog.py`) et post-vente (`_sell_dialog.py`)
- 🆕 Filtrage NaN/Inf dans `get_yahoo_history()` et `backfill_cours_historique()` (ceinture + bretelles)
- 🆕 Filtrage des faux tickers dans `backfill_cours_historique()` : regex ISIN + regex ticker valide (≤15 chars, pas d'espaces)
- 🆕 Commit incrémental ticker par ticker → un échec n'annule pas les autres
- 🆕 Mode WAL + `busy_timeout=30000` dans `database/db.py`
- 🆕 Achats/ventes fractionnaires sur toutes les catégories (`format='%.4f'`, `step=0.0001`)
- 🆕 `update_summary()` recalcule `m = q × p` au lieu de lire le champ `montant_input`
- 🆕 `update_qte_from_montant()` resynchronise le montant après arrondi (suppression de l'arrondi entier)
- 🆕 Module **`pages/portefeuille_detail/_releve_annuel.py`** :
  - `get_situation_at_date()` — rejoue les transactions jusqu'à une date cible
  - `get_available_years()` — liste des années avec données disponibles
  - `show_releve_annuel()` — popup détaillé avec KPIs et tableau
- 🆕 Menu déroulant "Relevé annuel" dans le header de la card Positions

### 🔜 Session 7 — Polish UI

- Zoom dynamique du graphique
- Indicateur de loading pendant backfill
- Supprimer les points sur les courbes
- Améliorations diverses

### 🔜 Plus tard

- Édition véritable des achats/ventes (extension de `_buy_dialog` et `_sell_dialog`)
- Édition des transactions de flux
- Harmonisation des catégories `'Fonds €'` / `'Fonds Euro'` (script de migration)
- Nettoyage du doublon `get_yahoo_price_at_date` dans `_yahoo.py`
- Export PDF/Excel du relevé annuel
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

❌ **Lancer plusieurs recherches sans debounce ni annulation**
- Spam des API Yahoo/Boursorama, résultats obsolètes qui écrasent les nouveaux
- ✅ Pattern : annuler la `task` précédente avant d'en créer une nouvelle, + `await asyncio.sleep(0.4)` au début

❌ **Chercher les titres "déjà connus" depuis les `Position`**
- Si un titre a été entièrement vendu, la `Position` n'existe plus → on le perd
- ✅ Source = `Transaction.distinct()` qui garde la trace même des titres revendus

❌ **🆕 Imbriquer `with get_session()` dans une fonction qui appelle elle-même un backfill**
- SQLite ne supporte qu'un seul écrivain → "database is locked"
- ✅ Détecter les infos nécessaires DANS la session courante avant `commit()`
- ✅ Appeler `backfill_*()` HORS du `with` (la session est garantie fermée)

❌ **🆕 Insérer des `NaN` ou `Inf` dans `cours_historique`**
- Yahoo retourne parfois des `NaN` pour les jours sans cotation
- Crash SQL : `NOT NULL constraint failed`
- ✅ Filtrer avec `math.isnan()` / `math.isinf()` dans `_yahoo.py` ET `backfill.py`

❌ **🆕 Passer un nom d'OPCVM ou un ISIN pur à `yfinance.history()`**
- Yahoo rejette → spam de logs `Invalid ISIN number` ou `possibly delisted`
- ✅ Filtrer en amont avec regex : ticker court (≤15 chars), pas d'espaces, pas un ISIN
- ✅ Les OPCVM doivent passer par Boursorama, pas Yahoo

❌ **🆕 `session.commit()` global à la fin d'un backfill multi-tickers**
- Si UN ticker plante, TOUS les inserts précédents sont rollbackés
- ✅ Commit incrémental ticker par ticker dans `backfill_cours_historique()`

❌ **🆕 Forcer `step=1` et `format='%g'` sur les "actions"**
- Yahoo classe parfois les ETF/ETC comme `EQUITY` (ex: XAD1.DE)
- L'utilisateur doit pouvoir acheter 3.15 parts
- ✅ Toujours utiliser `format='%.4f'` et `step=0.0001` partout

❌ **🆕 Lire `montant_input.value` dans le summary**
- Si l'utilisateur change le prix sans retaper la quantité, le montant n'est pas synchronisé
- ✅ Toujours recalculer `m = q × p` à l'affichage

❌ **🆕 Utiliser `Portefeuille.nom` (ça n'existe pas)**
- Le bon attribut est `Portefeuille.nom_affiche` (propriété calculée à partir de `type` + `proprietaire.prenom`)