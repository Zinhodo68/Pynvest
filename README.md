# 📊 Pynvest

> **AI-Optimized Documentation** — Ce README est conçu pour qu'une IA puisse comprendre rapidement l'architecture, le rôle de chaque fichier et le flux de données de l'application.

Webapp personnelle de gestion du patrimoine financier familial, développée en **Python + NiceGUI + SQLAlchemy + SQLite + ECharts**.

Pynvest permet de suivre plusieurs membres de la famille, plusieurs portefeuilles, différents types de supports d'investissement, et de visualiser l'évolution du patrimoine dans le temps avec récupération automatique des cours.

---

## 🎯 Vue d'ensemble pour une IA

**Domaine métier** : Gestion patrimoniale familiale (PEA, AV, PER, livrets, etc.).

**Stack technique** :
- **Frontend** : NiceGUI (Python → WebSocket → Vue.js/Quasar/Tailwind)
- **Backend** : Python 3.14, SQLAlchemy 2.0 (ORM)
- **Base de données** : SQLite en mode WAL (`patrimoine.db`)
- **Charts** : ECharts via `ui.echart()`
- **Données externes** : `yfinance` (Yahoo), `httpx + BeautifulSoup` (Boursorama scraping)

**Architecture logique** (flux de données) :
```
[Pages UI] → [Services] → [Database (SQLAlchemy)] → [patrimoine.db]
                ↓
        [Yahoo Finance API]
        [Boursorama scraping]
        [Backfill historique]
```

**Modèle de données** (5 entités principales) :
- `Membre` (personne physique de la famille)
- `Portefeuille` (PEA, AV, PER, livret, etc., lié à un membre)
- `Position` (ligne d'actif détenu : action, ETF, fonds €, cash…)
- `Transaction` (versement, retrait, achat, vente, dividende, frais, intérêts)
- `Valorisation` (snapshot quotidien de la valeur du portefeuille)
- `CoursHistorique` (historique journalier des cours par ticker/ISIN)
- `SupportLabel` (cosmétique : nom personnalisé pour un titre)

---

## 📁 Arborescence des fichiers et utilité de chacun

### 🟢 Racine du projet (`/`)

| Fichier | Rôle | Points clés pour l'IA |
|---|---|---|
| **`main.py`** | **Point d'entrée** de l'application NiceGUI. | 1. **Force le fallback pur Python de SQLAlchemy** (évite un bug Cython sur Python 3.14/Windows). 2. **Patch des processeurs de dates** (`secure_str_to_datetime`, `secure_str_to_date`, `secure_str_to_time`) pour tolérer les types inattendus dans la BDD. 3. Initialise la BDD (`init_db()`), expose `/uploads` en statique. 4. Déclare les **routes NiceGUI** : `/`, `/portefeuilles`, `/portefeuilles/{member}`, `/portefeuille/{pid}`, `/famille`, et les pages stub (`/immobilier`, `/comptes`, `/investissements`, `/marches`, `/parametres`). 5. Déclenche la MAJ des cours au démarrage via `app.on_startup(_startup_update_quotes)`. 6. Lance `ui.run(port=8080)`. |
| **`__init__.py`** | Fichier vide. Marque `Pynvest` comme package Python. | Pas de logique métier. |
| **`theme.py`** | Gestion du **thème dark/light** persistant (storage côté serveur NiceGUI). | Définit `get_is_dark()`, `set_is_dark()`, `apply_theme_script()` (injecte JS pour classe `dark` sur `<html>`), `init_theme()`, `get_colors()` (retourne dict avec `text_primary`, `text_secondary`, `card_bg`, `card_border`, `page_bg` selon mode). |
| **`requirements.txt`** | Dépendances Python verrouillées. | `nicegui==3.11.1`, `SQLAlchemy==2.0.49`, `yfinance==1.3.0`, `httpx>=0.28.1`, `beautifulsoup4>=4.14.3`, `lxml>=6.1.0`. |
| **`patrimoine.db`** | **Base SQLite** (engagée dans le repo comme exemple, ignorée en prod via `.gitignore`). | Mode WAL activé. Contient toutes les tables + fichiers `patrimoine.db-wal` et `patrimoine.db-shm` (temporaires). |
| **`.gitignore`** | Exclusions Git. | Ignore `.venv/`, `__pycache__/`, `*.pyc`, `patrimoine.db-wal/shm`, `patrimoine.db.backup`, `patrimoine.bak.db`, `uploads/`, `*.log`, `.env`, `app_state.json`. |
| **`.nicegui/`** | Dossier de cache NiceGUI (storage persistant, sessions). | Pas à modifier. |
| **`uploads/`** | Dossier pour les **logos** des portefeuilles uploadés (servi en `/uploads/`). | Créé automatiquement par `main.py` si absent. |

### 🟢 Scripts utilitaires (`/`)

| Fichier | Rôle |
|---|---|
| **`migrate.py`** | **Migration manuelle** de la BDD. À exécuter après une mise à jour du modèle. Ajoute les colonnes enrichies de `transactions` (`ticker`, `code`, `nom_titre`, `categorie`, `quantite`, `prix_unitaire`) et crée la table `support_labels` avec ses index, si manquants. Utilise du SQL brut via `sqlite3` (pas SQLAlchemy). |
| **`reset_data.py`** | **Reset DESTRUCTIF** d'un portefeuille. Supprime transactions, valorisations et positions classiques, **PRÉSERVE les Fonds €** (catégorie `Fonds €`/`Fonds Euro`) en les réinitialisant à quantité=0 et PRU=1.0. Optionnel : vider aussi `cours_historique`. Demande une confirmation "OUI". |
| **`test.py`** | Script de **test/recalcul des PRU**. Pour chaque position non-Cash/non-Fonds €, recalcule la quantité et le PRU en rejouant les transactions d'achat/vente du portefeuille. Mode DRY_RUN par défaut (`DRY_RUN=False` pour appliquer). Utile pour détecter des PRU désynchronisés. |
| **`fix_date.py`** | **Purge des données très anciennes** (avant 2017-01-01) dans `transactions`, `cours_historique`, `valorisations`. Exécute un `VACUUM` pour comprimer la BDD. |
| **`purge.py`** | Vide complètement la table `cours_historique`. Simple DELETE puis commit. |
| **`diagnostic_cash.py`** | **Diagnostic d'un portefeuille PEA** (hardcodé `PEA_ID = 2`). Rejoue toutes les transactions et compare les positions/cash **recalculés** vs **stockés en BDD**. Affiche les écarts en quantité et en €. Outil de debug pour comprendre un décalage de cash. |
| **`debug_buzzi.py`** | **Debug ciblé sur le titre "BUZZI"**. Liste toutes les positions et transactions contenant "BUZZI" dans nom/ticker/code. |

### 🟢 Base de données (`database/`)

| Fichier | Rôle | Points clés pour l'IA |
|---|---|---|
| **`database/db.py`** | **Configuration SQLAlchemy + factory de sessions**. | 1. Engine SQLite avec `check_same_thread=False`, `timeout=30`. 2. **Active les PRAGMAs** à chaque connexion via `@event.listens_for(engine, "connect")` : `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=30000`, `foreign_keys=ON`. 3. `SessionLocal = sessionmaker(autoflush=False, autocommit=False)`. 4. `init_db()` crée les tables manquantes + applique `_ensure_light_migrations()` (ALTER TABLE pour ajouter `date_cloture` sur `portefeuilles`). 5. **Fonctions de lecture optimisées** : `get_all_membres()`, `get_all_portefeuilles()`, `get_portefeuilles_by_membre()` → toutes utilisent `preload_stats()` pour éviter le N+1. |
| **`database/models.py`** | **Modèles SQLAlchemy** (schéma de la BDD) et **logique métier**. | Définit 6 classes : **`Membre`** (personne : prenom, nom, initiales, role, date_naissance, email, couleur, relation vers `portefeuilles`). **`Portefeuille`** (type, etablissement, date_creation, **date_cloture**, logo_path, url_gestion, notes, taux_interet/plafond pour mono-supports, **cache `_stats_cache`** pour les stats agrégées, propriétés calculées : `valorisation_actuelle`, `total_verse`, `plus_value`, `rendement_total_pct`, `rendement_annualise_pct` qui consultent le cache en priorité puis fallback lazy-loading, méthode `to_dict()` pour sérialisation). **`SupportLabel`** (cosmétique : nom personnalisé d'un titre avec `ticker`/`code`/`custom_name`/`original_name`, contrainte CHECK : au moins un identifiant non-null). **`Valorisation`** (snapshot date+montant). **`Transaction`** (date_operation, type_operation ∈ {versement, retrait, achat, vente, dividende, frais, interets}, montant, libellé, `parent_transaction_id` pour lier les arbitrages, **champs enrichis** : ticker, code, nom_titre, categorie, quantite, prix_unitaire). **`Position`** (ligne d'actif : nom, code, ticker, categorie, quantite, prix_moyen, cours_actuel, devise, auto_update, propriétés `prix_revient`, `valorisation`, `plus_value`, `plus_value_pct`). **`CoursHistorique`** (1 ligne par titre par jour : ticker, isin, date_cours, cours, devise, source). ⚠️ **Important** : événement SQLAlchemy `@event.listens_for(Position.prix_moyen, 'set')` qui alerte si le PRU chute de plus de 50% (probable bug). |

### 🟢 Services métier (`services/`)

| Fichier | Rôle |
|---|---|
| **`services/_yahoo.py`** | **Couche Yahoo Finance** (yfinance). `search_yahoo(query, limit)` filtre les `quoteType` ∈ {EQUITY, ETF, CRYPTOCURRENCY, INDEX} (exclut MUTUALFUND/OPCVM). `get_yahoo_price(symbol)` → prix actuel + devise via `fast_info`. `get_currency_rate(from, to)` pour conversion. `get_yahoo_history(symbol, start, end)` → historique journalier (filtre NaN/Inf). `get_yahoo_price_at_date(symbol, target_date)` → cours de clôture à une date (fenêtre 10j avant pour week-ends). |
| **`services/_boursorama.py`** | **Scraping Boursorama** pour les OPCVM/SICAV. `search_opcvm(query, limit)` interroge `/recherche/_instruments/{query}` et filtre les URLs contenant `/opcvm/` ou `/sicav/`, extrait l'ISIN via regex. `get_opcvm_price(url_or_isin)` scrape la page du fonds (sélecteur `.c-instrument--last`), parse "123,45 EUR" → 123.45. |
| **`services/_state.py`** | **État partagé** de l'app. 1. **État persistant JSON** (`app_state.json` à la racine) : `get_last_update_date()`, `set_last_update_date()`, `is_update_needed()` (True si dernière MAJ != aujourd'hui). 2. **État UI volatile** : `PortfolioFilterState` singleton avec `selected` (membres actifs), `membres_avec_pf` (membres ayant des portefeuilles), callbacks `dashboard_refresh` et `header_refresh`. La méthode `toggle(m_id)` ajoute/retire un membre (avec garde-fou : au moins 1 sélectionné) et déclenche les refreshes. |
| **`services/market_data.py`** | **Façade** qui dispatche vers Yahoo/Boursorama. Exporte `search_action_etf()`, `search_fonds_opcvm()`, `get_current_price_with_currency(symbol, source)`, `get_currency_rate()`, `get_price_at_date_with_currency(symbol, source, date)`. Réexporte aussi `unified_search` de `services.search`. |
| **`services/quotes_updater.py`** | **Mise à jour quotidienne des cours**. `update_all_quotes(force=False)` : si déjà fait aujourd'hui → no-op, sinon : 1. Charge toutes les positions (hors Cash/Fonds Euro). 2. Déduplique par ticker/code. 3. Pour chaque ticker unique, appelle `get_current_price_with_currency` (Yahoo si ticker, Boursorama si ISIN). 4. Convertit en EUR via `get_currency_rate` si devise ≠ EUR. 5. Insère dans `CoursHistorique` + met à jour `position.cours_actuel`. 6. **Fallback** pour échecs API : récupère le dernier cours de `CoursHistorique`, sinon le prix unitaire de la dernière transaction d'achat/vente pour ce titre exact. 7. Prend un **snapshot quotidien** dans `Valorisation` pour chaque portefeuille. 8. **Déclenche le backfill** automatique (reconstruction historique). |
| **`services/backfill.py`** | **Reconstruction de l'historique des valorisations**. Deux fonctions principales : **`backfill_cours_historique(pid)`** : télécharge incrémentalement les cours Yahoo pour chaque ticker valide (entre dernière date en BDD et aujourd'hui), reconstruit une série pour les actifs non-Yahoo (OPCVM) à partir des prix d'achat/vente saisis (`source='transaction'`). **`backfill_valorisations(pid)`** : supprime les anciennes valorisations puis rejoue **jour par jour** toutes les transactions du portefeuille pour calculer une valorisation quotidienne. Utilise des **pointeurs chronologiques O(1)** pour le forward-fill des cours. Gère correctement les **arbitrages internes** (parent_transaction_id). Nettoie les positions soldées (tolérance epsilon). Met à jour `position.cours_actuel` avec le DERNIER COURS CONNU (et non plus le PRU). |
| **`services/search.py`** | **Recherche unifiée** de titres. `unified_search(query)` exécute en parallèle (asyncio) : BDD locale + Yahoo + Boursorama. **Détecte automatiquement les ISIN** (regex `^[A-Z]{2}[A-Z0-9]{9}\d$`) → route prioritaire Boursorama. `search_in_db(query)` cherche dans les transactions passées (distinct par ticker/code/nom_titre), exclut Cash/Fonds €, **enrichit** avec les portefeuilles où le titre est encore détenu (`in_portfolios`). Retourne un dict groupé : `{db: [...], yahoo: [...], boursorama: [...], is_isin: bool}`. |
| **`services/portfolio_stats.py`** | **⚡ Optimisation N+1**. `preload_stats(session, portefeuilles)` exécute **UNE SEULE requête SQL agrégée** (3 sous-requêtes : `valo_sq`, `verse_sq`, `nb_tx_sq`) avec SUM, CASE, COUNT pour calculer pour chaque portefeuille : valorisation_actuelle, total_verse (hors arbitrages via `parent_transaction_id IS NULL`), nb_transactions. Remplit `Portefeuille._stats_cache`. Si valorisation = 0 et qu'il existe des `valorisations`, utilise la dernière valorisation manuelle. Les `@property` du modèle consultent ce cache en priorité (0 lazy-load) puis fallback sur le lazy-loading historique → **backward compatible**. `preload_single(session, pid)` : raccourci pour 1 portefeuille. |
| **`services/perf_annuelle.py`** | **Calcul des performances annuelles** (Modified Dietz par année civile) et **performance annualisée** (XIRR). `get_rendements_annuels(pid, max_years=10)` calcule pour chaque année depuis la première transaction : rendement via Modified Dietz en tenant compte des flux externes pondérés par leur durée. `get_rendement_annualise_time_weighted(pid)` utilise désormais **XIRR** sur les flux externes datés + valorisation courante (plus fiable que la composition des rendements annualisés Dietz). Pour la période courante (target >= today), utilise la **valorisation courante** (stats agrégées) plutôt qu'une reconstruction historique. |
| **`services/perf_xirr.py`** | **Implémentation du TRI/XIRR**. `_xirr(flows)` calcule le TRI par bissection (low=-0.9999, high=10.0) avec NPV classique. Convention : versement = flux négatif, retrait/valorisation finale = flux positif. `get_xirr_for_portefeuilles(pids, current_value)` agrège les flux externes (hors arbitrages) sur plusieurs portefeuilles et ajoute la valorisation finale à aujourd'hui. |
| **`services/labels.py`** | **Noms personnalisés des supports** (cosmétique). `get_display_name(ticker, code, fallback)` retourne le `custom_name` depuis `SupportLabel` si existant, sinon le fallback (nom Yahoo/Boursorama). `set_custom_name(ticker, code, custom_name, original_name=None)` : upsert. `delete_custom_name(ticker, code)` : supprime le label. |

### 🟢 Composants UI partagés (`components/`)

| Fichier | Rôle |
|---|---|
| **`components/layout.py`** | **Layout principal** de chaque page. `page_layout(active_route)` : 1. Nettoie les callbacks de refresh. 2. Initialise le thème + toggle dark/light. 3. Récupère les couleurs. 4. Applique `background-color` sur `body`, `.q-page`, `.nicegui-content`. 5. Crée la sidebar (drawer fixe) et le header. Retourne `is_dark` (bool). |
| **`components/header.py`** | **Header** de l'app (barre supérieure). Contient `create_header(toggle_fn, drawer)` : bouton hamburger pour le drawer, titre "Situation Patrimoniale", **badges cliquables des membres** (`render_header_badges()` qui est `@ui.refreshable` et s'enregistre dans `portfolio_state.header_refresh`) avec logique de sélection multiple (membre sans PF = grisé inactif, sélectionné = couleur vive, non-sélectionné = grisé clair cliquable). Boutons "Documents", "Tâches" (stubs visuels) et toggle dark/light. |
| **`components/sidebar.py`** | **Sidebar/Navigation**. Menu avec items : Tableau de bord (`/`), Portefeuilles (`/portefeuilles` + sous-items par membre), Immobilier, Comptes, Investissements, Famille, Marchés. **Conteneur réactif** : se redessine quand `refresh_layout()` est appelé (après ajout/suppression d'un membre). État "expanded" géré en mémoire par item parent. |
| **`components/refresh.py`** | **Système de rafraîchissement partagé**. Liste de callbacks `_callbacks`. `register_refresh_callback(cb)` ajoute un callback. `refresh_layout()` les exécute tous. `clear_callbacks()` à appeler au début de chaque page (évite l'accumulation entre pages). |

### 🟢 Pages (`pages/`)

#### Pages principales

| Fichier | Rôle |
|---|---|
| **`pages/__init__.py`** | Package marker (vide). |
| **`pages/dashboard.py`** | **Page d'accueil `/`**. Affiche un **bandeau de santé patrimoniale** (statique : "82", couleur verte), 5 **KPI cards** (VALEUR BRUTE, ENDETTEMENT, PATRIMOINE NET, RÉVALORISATION, REVENUS MENSUELS - valeurs hardcodées, à connecter aux données), un **tableau rendement des actifs** (statique) et une **card allocation d'actifs** (camembert ECharts avec 3 catégories : Immobilier 73.1%, Actifs Financiers 23.8%, Trésorerie 4.0%). ⚠️ **Page encore statique** (mockup). |
| **`pages/famille.py`** | **Page `/famille`** : gestion des membres familiaux. Affiche une **grille de cartes** par membre (avatar avec initiales + couleur, nom, rôle, email, date de naissance). Dialogue d'ajout/édition avec : prénom, nom, initiales (auto-générées), rôle (Père/Mère/Enfant/Conjoint(e)/Autre), date de naissance (input français JJ/MM/AAAA avec datepicker), email, **sélection de couleur** (6 boutons pastilles). Menu contextuel : Modifier/Supprimer avec confirmation. |
| **`pages/portfolios.py`** | **Page `/portefeuilles`** : liste des portefeuilles (avec ou sans filtre par membre via `/portefeuilles/{member}`). En-tête : avatar + nom du membre + bouton "Nouveau portefeuille". **Charge via `preload_stats()`** (1 query SQL). **Bandeau de KPIs globaux** (valorisation totale, total versé, etc.). **Bandeau dépliable** : graphique d'évolution du patrimoine agrégé. **Grille de cartes** par portefeuille (cliquables → `/portefeuille/{pid}`). **Section portefeuilles clôturés** (discrète). |
| **`pages/portefeuilles_data.py`** | **Données de référence** des types de portefeuille. Liste `TYPES_PORTEFEUILLE` (PEA, PEA-PME, PER, CTO, Assurance-Vie, Livret A/Bleu, LDDS, Livret Jeune, LEP, Crowdfunding, Crypto, Compte Épargne, Autre). Chaque type a : `value`, `label`, `icon`, `couleur`, `mode` (`'mono'` ou `'multi'`), et pour les livrets : `plafond` et `taux_defaut`. Fonctions : `get_type_info(value)`, `is_mono_support(value)`. |
| **`pages/positions_data.py`** | **Catégories de positions**. Liste `CATEGORIES_POSITION` (Cash, Action, ETF, Fonds, SCPI, Obligation, Crypto, Fonds €, UC, Projet, Autre) avec icon/couleur. Fonction `get_categorie_info(value)`. |

#### Pages stub (non implémentées)

| Fichier | Rôle |
|---|---|
| **`pages/comptes.py`** | Page `/comptes` stub (placeholder "Liste de vos biens immobiliers."). |
| **`pages/immobilier.py`** | Page `/immobilier` stub. |
| **`pages/investissements.py`** | Page `/investissements` stub. |
| **`pages/marches.py`** | Page `/marches` stub. |
| **`pages/parametres.py`** | Page `/parametres` stub. |

#### Sous-package détail portefeuille (`pages/portefeuille_detail/`)

C'est la page **la plus riche** de l'app, décomposée en 10 modules préfixés par `_`.

| Fichier | Rôle |
|---|---|
| **`pages/portefeuille_detail/__init__.py`** | Package marker (vide). |
| **`pages/portefeuille_detail/_content.py`** | **Orchestrateur principal** de la page détail. `render(pid)` : charge le portefeuille, appelle `preload_stats()`, sérialise en `data`. Définit `render_chart_card()` en `@ui.refreshable` (pour rafraîchir le graphique après MAJ cours). Délègue à `_header.py`, `_chart.py`, `_positions.py` (ou `_mono_support.py`), `_transactions.py`. Distingue **mono-support** (livrets) vs **multi-support** (PEA, AV, etc.). |
| **`pages/portefeuille_detail/_header.py`** | **En-tête + KPIs** de la page détail. `render_header()` : bouton retour, logo (image ou icône), nom affiché, badge propriétaire avec initiales, bouton site externe, bouton refresh (avec animation d'icône), bouton edit, bouton "+ Valorisation". Infos : date d'ouverture, établissement, propriétaire, nombre de transactions, notes. `render_kpis()` : **5 KPI cards** (VALORISATION, CAPITAL INVESTI, +/- VALUE ou INTÉRÊTS, PERF. TOTALE, **PERF. ANNUALISÉE** expandable). Helpers : `_is_context_valid()`, `_safe_notify()` (protègent contre les crashes "Client has been deleted"). État d'expansion global `_kpi_expand_state` partagé. |
| **`pages/portefeuille_detail/_chart.py`** | **Graphique ECharts** d'évolution de la valorisation. `render_chart(valorisations, transactions, color, c, is_dark)` : prépare les dates triées, sépare les apports externes (filtre `parent_transaction_id IS NULL`), calcule les 4 séries (Valorisation, Capital investi, +/- value, Rendement) en timestamps ms. Tooltip custom en français avec emojis (📅 💎 💰 ✅/❌). Axe X en `type='time'` (timestamps ms), bornes Y dynamiques (`compute_bounds`), zoom + dataZoom slider. Séries "Capital investi" et "+/- value" sont **invisibles** (opacity=0) mais présentes pour le tooltip. |
| **`pages/portefeuille_detail/_positions.py`** | **Section positions** + dialogue de renommage. `render_positions_section()` : tableau colonnes (Titre, Quantité, PRU, Cours, Valorisation, +/-). **Sépare visuellement** les titres des **réserves de liquidités** (Cash, Fonds €, Fonds Euro) par une ligne pointillée "💰 Réserves de liquidités". Menu contextuel (clic droit) sur chaque titre : Acheter / Vendre / Renommer / Supprimer. **`_render_rename_dialog`** : permet de définir un `custom_name` via `services.labels.set_custom_name()`, avec bouton "Réinitialiser" qui appelle `delete_custom_name()`. **Note** : Cash/Fonds € ne sont pas concernées par le renommage. |
| **`pages/portefeuille_detail/_buy_dialog.py`** | **Dialogue d'achat** avec recherche unifiée. `open_buy_dialog()` : 1. Affiche le cash disponible (ou Fonds € dispo pour AV/PER). 2. **Champ de recherche** avec debounce 0.4s, annulation de la requête en cours si nouvelle saisie (`search_task.cancel()`). 3. Appelle `unified_search()` (BDD + Yahoo + Boursorama). 4. **Affiche 4 groupes** : "📁 DÉJÀ DANS VOS PORTEFEUILLES", "🌐 YAHOO FINANCE", "📊 BOURSORAMA", "➕ CRÉER UN NOUVEAU SUPPORT". 5. Pour un actif externe : récupère le cours actuel via `get_current_price_with_currency`. 6. Formulaire de saisie : date (JJ/MM/AAAA), prix unitaire (pré-rempli avec cours actuel ou historique), quantité, montant. 7. À la sauvegarde : crée `Transaction(type='achat')`, met à jour la `Position` (PRU recalculé, quantité augmentée), décrémente le Cash, déclenche `backfill` async. |
| **`pages/portefeuille_detail/_sell_dialog.py`** | **Dialogue de vente**. `open_sell_dialog()` : 1. Liste les positions vendables (quantité > 0, hors Cash/Fonds €). 2. Pour AV/PER : propose aussi de vendre des **Fonds €**. 3. **Auto-remplissage du prix de vente** : récupère le cours actuel (si aujourd'hui) ou historique via `get_price_at_date_with_currency` (gère conversion devises). 4. Préserve la saisie manuelle (drapeau `manually_modified`). 5. À la sauvegarde : crée `Transaction(type='vente')`, met à jour `Position` (quantité diminuée), incrémente le Cash. |
| **`pages/portefeuille_detail/_dividende_dialog.py`** | **Dialogue d'enregistrement de dividende**. `open_dividende_dialog()` : 1. Liste les positions éligibles (hors Cash/Fonds €). 2. Saisie : montant brut, montant net (auto-rempli à partir du brut si vide), date, notes. 3. Option "Créditer le Cash" (par défaut True). 4. Résumé en temps réel. 5. À la sauvegarde : crée `Transaction(type='dividende', montant=net)`, **met à jour le PRU** (caractéristique : un dividende réinvesti augmente la quantité), crédite éventuellement le Cash via `ajuster_cash`. |
| **`pages/portefeuille_detail/_operations_dialogs.py`** | **Dialogues d'opérations de flux** (versement, retrait, frais, intérêts). Ouvre des formulaires typés par opération, mettant à jour le cash et les positions selon le type. |
| **`pages/portefeuille_detail/_transactions.py`** | **Card des transactions** + filtres. Constantes visuelles `TYPE_COLORS`, `TYPE_ICONS`, `TYPE_LABELS` (pour les 7 types). Helpers : `_run_backfill_async()` (lance le backfill via `asyncio.to_thread` avec notification ongoing), `_extract_unique_assets()` (pour le filtre par actif), `_apply_filters()` (filtres : types, asset, date_from, date_to, search texte), `_count_active_filters()`, `_get_historical_assets()` (titres historiquement détenus mais plus en position, pour dividendes tardifs). `render_transactions_card()` : header avec compteur + bouton filtre (badge dynamique du nombre de filtres actifs), liste des transactions principales avec leurs frais enfants rattachés, **menu contextuel** sur chaque ligne (Modifier/Supprimer). |
| **`pages/portefeuille_detail/_releve_annuel.py`** | **Popup "Relevé annuel"** au 31/12. `get_situation_at_date(pid, target_date)` : rejoue toutes les transactions jusqu'à `target_date` (comme le backfill mais en one-shot). **Calcule** : positions détenues (quantité, PRU, cours à la date, valorisation, +/- value), cash, total_verse (flux externes uniquement, hors arbitrages), valo_totale, plus_value. `get_available_years(pid)` : liste des années depuis la première transaction. `show_releve_annuel(pid, year, c, is_dark)` : affiche la popup NiceGUI avec le détail du portefeuille à la date demandée. ⚠️ Les **réserves de liquidités** (Cash/Fonds €) sont séparées visuellement. |
| **`pages/portefeuille_detail/_mono_support.py`** | **Section mono-support** (livrets). `render_mono_support_section()` : affiche taux d'intérêt, plafond (avec barre de progression % utilisé), disponible avant plafond, **estimation des intérêts annuels** (valo × taux). `_open_mono_dialog()` : édition du taux/plafond. `open_valorisation_dialog()` : saisie d'une **valorisation manuelle** (snapshot à une date) — utile pour les livrets qui n'ont pas de cours quotidien. |
| **`pages/portefeuille_detail/_cash_helpers.py`** | **Helpers de gestion du Cash**. `impact_cash(type_operation, montant)` : retourne le signe de l'impact (+ pour versement/dividende/vente, - pour retrait/frais/achat). `ajuster_cash(session, pid, delta)` : ajuste la position 'Cash' du portefeuille (crée la position si absente, sinon incrémente). Utilisé par tous les dialogues de transaction. |

### 🟢 Utilitaires (`utils/`)

| Fichier | Rôle |
|---|---|
| **`utils/formatters.py`** | **Formatters français**. `format_money(value, currency='€', decimals=0)` → `"12 345 €"` (espace pour milliers, virgule décimale). `format_percent(value, decimals=2, with_sign=True)` → `"+12,45 %"`. `format_date_fr(value)` → `"31/12/2025"`. `get_perf_color(value)` → `'#10b981'` (vert) si >0, `'#ef4444'` (rouge) si <0, `'#94a3b8'` (gris) si 0/None. |

---

## 🔁 Flux complets pour une IA

### Flux 1 : Démarrage de l'app
```
python main.py
  ↓
[Patchs SQLAlchemy cyextension] → bloque l'extension Cython buggée
  ↓
[Patch secure_str_to_*] → processeurs de dates tolérants
  ↓
init_db() → crée tables manquantes + _ensure_light_migrations()
  ↓
Déclaration des routes : /, /portefeuilles, /famille, /portefeuille/{pid}, stubs
  ↓
app.on_startup(_startup_update_quotes) → MAJ cours au démarrage
  ↓
ui.run(port=8080) → serveur NiceGUI
```

### Flux 2 : Affichage d'un portefeuille (route `/portefeuille/{pid}`)
```
URL /portefeuille/5
  ↓
main.py : portefeuille_detail_page(pid=5)
  ↓
pages/portefeuille_detail/_content.py : render(5)
  ↓
  - page_layout() : thème + header (badges membres) + sidebar
  - session.get(Portefeuille, 5)
  - preload_stats() → 1 query SQL agrégée → remplit _stats_cache
  - serialise en data + valorisations + transactions + positions
  ↓
  render_header() (header + 5 KPIs)
  render_chart_card() (bandeau dépliable avec ECharts)
  ↓
  Si mono-support :
    render_mono_support_section() (taux/plafond)
  Sinon :
    render_positions_section() (tableau)
  ↓
  render_transactions_card() (card latérale ou dessous)
```

### Flux 3 : Achat d'un titre
```
Clic "Acheter" sur une position (ou menu contextuel)
  ↓
open_buy_dialog() (_buy_dialog.py)
  ↓
  - Récupère cash disponible
  - Champ de recherche (avec debounce 400ms)
  - unified_search() → asyncio.gather(search_in_db, search_yahoo, search_opcvm)
  - Affichage groupé : BDD / Yahoo / Boursorama / Créer
  ↓
  Sélection d'un actif :
    - Si externe : get_current_price_with_currency() → pré-remplissage prix
    - Saisie : date, prix unitaire, quantité
  ↓
  Save :
    1. Transaction(type='achat', ticker, code, nom_titre, prix_unitaire, quantite)
    2. Position : PRU recalculé, quantité augmentée
    3. ajuster_cash() : décrémente Cash
    4. _run_backfill_async() → backfill_cours_historique() + backfill_valorisations()
    5. refresh_layout() → redessine header/sidebar
    6. refresh_chart() → redessine le graphique ECharts
```

### Flux 4 : Backfill historique (reconstruction des valorisations)
```
Trigger : MAJ cours quotidienne OU après transaction impactante
  ↓
backfill_cours_historique(pid) :
  1. Liste tickers Yahoo valides (≠ ISIN, ≠ libellé)
  2. Pour chaque ticker, détermine la date de début (dernière en BDD + 1j)
  3. Télécharge get_yahoo_history(ticker, start, today) [hors session SQL]
  4. Convertit en EUR si devise ≠ EUR
  5. Insère dans CoursHistorique (anti-doublon ticker+date)
  6. Pour actifs non-Yahoo (OPCVM) : insère prix depuis transactions (source='transaction')
  ↓
backfill_valorisations(pid) :
  1. Supprime anciennes valorisations
  2. Charge cours historiques indexés par identifiants (ticker/ISIN)
  3. Tri chronologique, pointeurs forward-fill (O(1) amorti)
  4. Rejoue jour par jour les transactions du portefeuille :
     - Pour chaque transaction, applique son effet (cash + positions_held)
     - Gestion des arbitrages (parent_transaction_id)
     - PRU recalculé sur achats/dividendes réinvestis
     - Nettoyage positions soldées (epsilon 1e-9)
  5. À chaque jour : calcule valo_titres = Σ(qte × cours_forward_filled)
  6. Crée Valorisation(date, valo_totale = cash + valo_titres)
  7. Met à jour position.cours_actuel avec DERNIER COURS CONNU (pas PRU)
```

### Flux 5 : Calcul des KPI Valorisation d'un portefeuille
```
Portefeuille.valorisation_actuelle  (Portefeuille.to_dict → affiché dans le tableau)
  ↓
  Priorité 1 : _stats_cache (si preload_stats appelé)
    → retour de _stats_cache['valorisation_actuelle']
  ↓
  Priorité 2 : fallback lazy-loading
    → sum(pos.valorisation for pos in self.positions)
      où pos.valorisation = quantite × cours_actuel (si non null) ou prix_revient
  ↓
  Priorité 3 : si pas de positions, dernière Valorisation.montant
```

---

## 🧠 Règles métier importantes

| Règle | Pourquoi | Implémentation |
|---|---|---|
| **Arbitrages internes** = 2 transactions liées via `parent_transaction_id` | Ne pas gonfler artificiellement le capital investi | `backfill.py`, `_releve_annuel.py` : exclut via `t.parent_transaction_id IS NOT NULL` |
| **Capital investi** = uniquement flux externes (`versement`/`retrait` sans parent) | Éviter de compter 2x un transfert interne | `services/portfolio_stats.py` : `Transaction.parent_transaction_id.is_(None)` |
| **PRU** = moyenne pondérée des achats (et dividendes réinvestis) | Calcul correct du prix de revient | `Position.prix_moyen` recalculé sur chaque `achat`/`dividende` |
| **`_stats_cache`** : cache non-persisté sur l'instance Portefeuille | Éliminer N+1 lazy-loading (1 query SQL agrégée au lieu de ~4N) | `services/portfolio_stats.py` + propriétés du modèle |
| **`auto_update=False`** sur une Position → prix saisi manuellement | Certains titres (fonds maison) ne sont pas sur Yahoo | `services/quotes_updater.py` : section FALLBACK |
| **Cours pour les non-Yahoo** : reconstruit depuis prix d'achat/vente saisis (`source='transaction'`) | OPCVM/SICAV/fonds maison indisponibles sur Yahoo | `services/backfill.py` : section "Cours reconstruits" |
| **Cash position** = pseudo-Position avec `nom='Cash'`, `prix_moyen=1.0` | Le cash est un actif comme un autre | `pages/portefeuille_detail/_cash_helpers.py` |
| **Fonds €** = catégorie réservée (jamais supprimée au reset) | Structure obligatoire des AV/PER | `RESERVES_CATEGORIES = ('Fonds €', 'Fonds Euro')` |
| **Renommage cosmétique** : `SupportLabel` mappe ticker/ISIN → custom_name | Affichage user-friendly (APPLE INC → Apple) sans toucher au ticker | `services/labels.py` |
| **Patch SQLAlchemy cyextension** : force fallback pur Python | Bug "TypeError: fromisoformat: argument must be str" sur Python 3.14/Windows | `main.py` : `sys.modules['sqlalchemy.cyextension'] = None` |
| **Patch processeurs de dates** : `secure_str_to_datetime/date/time` | Tolérer types inattendus en BDD (entiers, mal formés) | `main.py` : override `py_processors.str_to_*` |
| **Axe X ECharts en `type='time'`** avec timestamps ms | Jamais en `type='category'` avec strings ISO (bug d'affichage) | `pages/portefeuille_detail/_chart.py` |
| **NaN/Inf interdits** dans `CoursHistorique` | Crash ECharts | `services/_yahoo.py`, `services/backfill.py` : `if math.isnan(...)` |
| **Backfill hors session SQL** (réseau) puis insertion | Évite de bloquer SQLite | `services/backfill.py` : 2 phases (réseau → insertion) |
| **Performance annualisée = XIRR** sur flux externes + valo courante | Plus fiable que composition des Dietz | `services/perf_xirr.py` + `services/perf_annuelle.py` |

---

## 🗃️ Schéma de base de données

```sql
membres           (id, prenom, nom, initiales, role, date_naissance, email, couleur, created_at)
portefeuilles     (id, type, etablissement, date_creation, date_cloture, logo_path,
                   url_gestion, notes, proprietaire_id → membres, taux_interet, plafond, created_at)
positions         (id, portefeuille_id → portefeuilles, nom, code, ticker, categorie,
                   quantite, prix_moyen, cours_actuel, devise, notes, date_ouverture,
                   auto_update, last_update, created_at, updated_at)
transactions      (id, portefeuille_id → portefeuilles, date_operation, type_operation,
                   montant, libelle, parent_transaction_id → transactions,
                   ticker, code, nom_titre, categorie, quantite, prix_unitaire, created_at)
valorisations     (id, portefeuille_id → portefeuilles, date_valeur, montant, created_at)
cours_historique  (id, ticker, isin, date_cours, cours, devise, source, created_at)
                   + INDEX sur ticker, isin, date_cours
support_labels    (id, ticker, code, custom_name, original_name, created_at, updated_at)
                   + CHECK (ticker IS NOT NULL OR code IS NOT NULL)
                   + INDEX sur ticker, code
```

---

## ⚡ Performance (points d'optimisation clés)

| Optimisation | Fichier | Impact |
|---|---|---|
| **Stats agrégées SQL** (1 query au lieu de N+1) | `services/portfolio_stats.py` | ×N réduction du nombre de queries |
| **`selectinload()`** sur proprietaire/positions/transactions | `database/db.py`, `pages/portfolios.py` | Élimine lazy-loading |
| **Cache `_stats_cache`** sur Portefeuille (ClassVar) | `database/models.py` | 0 requêtes supplémentaires après preload |
| **Backfill hors session SQL** | `services/backfill.py` | SQLite non bloqué pendant requêtes réseau |
| **Pointeurs chronologiques O(1)** pour forward-fill | `services/backfill.py` : `cours_index_pointers` | Reconstruction rapide sur gros historiques |
| **Async I/O via `asyncio.to_thread`** | `_transactions.py`, `_buy_dialog.py` | UI réactive pendant calculs longs |
| **Anti-doublon** à l'insertion cours (set de tuples) | `services/backfill.py` | Évite insertions inutiles |

---

## 🚀 Lancement rapide

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Activer l'environnement virtuel (Windows)
.venv\Scripts\activate

# 3. (Optionnel) Migrer la BDD si nouvelle version
python migrate.py

# 4. (Optionnel) Reset des données (⚠️ destructif)
python reset_data.py

# 5. Lancer l'app
python main.py

# 6. Ouvrir http://localhost:8080
```

---

## 🧪 Scripts de maintenance

| Script | Quand l'utiliser |
|---|---|
| `python migrate.py` | Après ajout de colonnes/modèles, pour mettre à jour une BDD existante |
| `python reset_data.py` | Pour vider les données d'un portefeuille (⚠️ DESTRUCTIF, garde les Fonds €) |
| `python test.py` | Pour vérifier/corriger les PRU (mode DRY_RUN par défaut) |
| `python fix_date.py` | Pour purger les données avant 2017 et compresser (VACUUM) |
| `python purge.py` | Pour vider complètement l'historique des cours |
| `python diagnostic_cash.py` | Pour débugger un décalage de cash sur le PEA #2 |
| `python debug_buzzi.py` | Pour inspecter les positions/transactions "BUZZI" |

---

## 🛣️ État du projet (résumé)

### ✅ Stable
- Gestion membres/portefeuilles/positions
- Cours Yahoo + Boursorama (OPCVM)
- Historique + reconstruction valorisations
- Backfill automatique après opérations
- Recherche unifiée (BDD + Yahoo + Boursorama)
- Renommage cosmétique des supports
- Stats SQL agrégées (perf)
- Mono-supports (livrets) avec taux/plafond
- Arbitrages internes (via parent_transaction_id)
- Relevé annuel au 31/12

### 🟡 En cours / à améliorer
- Adaptation dynamique du zoom du graphique
- Loader visuel pendant les backfills
- Quelques pages stubs (`/immobilier`, `/comptes`, etc.) non implémentées
- `dashboard.py` encore statique (KPIs hardcodés)

### ⚠️ Limitations connues
- Pas d'édition directe des achats/ventes/transactions de flux
- SCPI mal gérées
- Pas de gestion des splits
- Pas d'auth ni multi-utilisateur
- Pas de sauvegarde automatique
- Pas d'export PDF/Excel
- Performance du backfill perfectible sur gros historiques

---

## 🏷️ Auteur
Projet développé par **[Zinhodo68](https://github.com/Zinhodo68)** — usage local privé, mono-utilisateur, sans authentification.

GitHub : https://github.com/Zinhodo68/Pynvest
