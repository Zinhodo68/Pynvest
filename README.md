# 📊 Pynvest

Webapp personnelle de gestion du patrimoine financier familial, développée en **Python + NiceGUI + SQLAlchemy + SQLite + ECharts**.

Pynvest permet de suivre plusieurs membres de la famille, plusieurs portefeuilles, différents types de supports d’investissement, et de visualiser l’évolution du patrimoine dans le temps avec récupération automatique des cours.

> Usage local privé, mono-utilisateur, sans authentification pour le moment.

---

## ✨ Fonctionnalités

### Gestion du patrimoine
- Gestion de plusieurs **membres**
- Création de plusieurs **portefeuilles** par membre
- Support de plusieurs types de portefeuilles :
  - PEA
  - Compte-titres
  - Assurance-vie
  - PER
  - Livrets / mono-supports
  - autres variantes assimilées

### Supports suivis
- Actions
- ETF
- OPCVM / SICAV
- Crypto
- Fonds €
- Cash
- Supports manuels

### Données de marché
- Récupération des cours actuels via :
  - **Yahoo Finance**
  - **Boursorama**
- Historique des cours via **yfinance**
- Reconstruction historique des valorisations depuis les transactions

### Historique & analyse
- Graphique d’évolution du portefeuille
- Historique des valorisations jour par jour
- Relevé annuel détaillé au **31/12** de chaque année passée
- Calcul du capital investi
- Calcul de la valorisation, du cash, de la +/- value

### Transactions prises en charge
- Versements
- Retraits
- Achats
- Ventes
- Dividendes distribués en cash
- Dividendes réinvestis en parts
- Intérêts sur Fonds €
- Frais en euros
- Frais en parts

### UX / qualité de vie
- Recherche unifiée d’un support à l’achat :
  - BDD locale
  - Yahoo Finance
  - Boursorama
- Achats / ventes fractionnaires sur toutes les catégories
- Tri visuel des titres et des réserves de liquidités
- Renommage personnalisé des supports d’investissement
- Recalcul automatique de l’historique après achat / vente / transaction impactante

---

## 🆕 Renommage personnalisé des supports

Pynvest permet de définir un **nom d’affichage personnalisé** pour un support d’investissement.

### Pourquoi ?
Les noms renvoyés par Yahoo Finance ou Boursorama sont parfois :
- trop longs
- en majuscules
- peu lisibles
- peu pertinents pour l’interface

Exemples :
- `APPLE INC`
- `AMUNDI ETF MSCI WORLD UCITS ETF`
- `LVMH MOET HENNESSY LOUIS VUITTON`

Peuvent devenir :
- `Apple`
- `Amundi MSCI World`
- `LVMH`

### Principe
Le renommage est **purement cosmétique** :

- ✅ le **ticker Yahoo** ou le **code ISIN** reste inchangé
- ✅ la récupération des cours continue de fonctionner normalement
- ✅ les données historiques ne sont pas modifiées
- ✅ seul l’affichage dans l’interface utilise le nom personnalisé

### Portée
Le renommage est **global dans l’application** pour un même support identifié par :
- un `ticker` Yahoo
- ou un `code` ISIN

### Où le nom personnalisé est affiché ?
- liste des positions
- dialogue de vente
- liste des transactions
- relevé annuel

### Où renommer un support ?
Depuis la **liste des positions**, via l’icône **✏️** sur une ligne de titre.

> Les réserves de liquidités (`Cash`, `Fonds €`, `Fonds Euro`) ne sont pas concernées.

---

## 🧱 Stack technique

- **Python 3.14**
- **NiceGUI**
- **SQLAlchemy**
- **SQLite**
- **ECharts**
- **yfinance**
- Scraping Boursorama pour certains OPCVM / SICAV

Environnement de développement actuel :
- **PyCharm**
- **Windows**
- environnement virtuel `.venv`

---

## 📁 Structure du projet

```text
Pynvest/
├── main.py
├── migrate.py
├── reset_data.py
├── database/
│   ├── db.py
│   └── models.py
├── services/
│   ├── _boursorama.py
│   ├── _yahoo.py
│   ├── _state.py
│   ├── market_data.py
│   ├── quotes_updater.py
│   ├── backfill.py
│   ├── search.py
│   ├── positions_data.py
│   └── labels.py                # noms personnalisés des supports
├── pages/
│   ├── dashboard/
│   ├── membres/
│   ├── portefeuilles/
│   ├── portefeuilles_data.py
│   ├── positions_data.py
│   └── portefeuille_detail/
│       ├── __init__.py
│       ├── _content.py
│       ├── _header.py
│       ├── _stats.py
│       ├── _chart.py
│       ├── _positions.py
│       ├── _transactions.py
│       ├── _buy_dialog.py
│       ├── _sell_dialog.py
│       ├── _releve_annuel.py
│       ├── _mono_support.py
│       └── _cash_helpers.py
├── components/
├── theme/
├── utils/
│   └── formatters.py
└── uploads/
🚀 Lancement du projet
1. Activer l’environnement virtuel
Sous Windows :

Bash

.\.venv\Scripts\activate
2. Lancer l’application
Bash

python main.py
3. Ouvrir l’application
NiceGUI affichera l’URL locale dans le terminal, généralement :

text

http://localhost:8080
🗄️ Base de données
La base SQLite utilisée est :

text

patrimoine.db
Elle est stockée à la racine du projet.

Configuration SQLite robuste
Le fichier database/db.py active automatiquement :

WAL (Write-Ahead Logging)
busy_timeout=30000
synchronous=NORMAL
foreign_keys=ON
Fichiers générés par SQLite
En mode WAL, SQLite génère aussi :

patrimoine.db-wal
patrimoine.db-shm
À ignorer dans Git.

🧩 Schéma de données
Modèles principaux
Membre
Portefeuille
Position
Transaction
Valorisation
CoursHistorique
Modèle supplémentaire : SupportLabel
Utilisé pour stocker les noms personnalisés des supports.

Champs :

id
ticker
code
custom_name
original_name
created_at
updated_at
Règle :

au moins un des deux champs ticker ou code doit être renseigné
🏗️ Principe d’architecture : Position vs Transaction
Pynvest utilise une approche hybride :

Concept	Source de vérité	Usage
État actuel	Position	affichage rapide des cartes, KPIs, tableaux
Historique	Transaction	backfill, graphique, relevés annuels
Avantages
affichage rapide de l’état courant
reconstruction historique fidèle
pas de recalcul lourd à chaque page
🔁 Arbitrages internes
Les arbitrages sont modélisés avec 2 transactions liées via parent_transaction_id.

Exemple : Fonds € → Titre
transaction parent : achat
transaction enfant : vente du Fonds €
Exemple : Titre → Fonds €
transaction parent : vente
transaction enfant : versement vers Fonds €
Règles
le capital investi ne compte que les flux externes
les arbitrages internes n’impactent pas artificiellement le cash
le backfill tient compte des parents et enfants d’arbitrage
🔍 Recherche unifiée à l’achat
Le dialogue d’achat repose sur un champ unique qui interroge en parallèle :

la base locale
Yahoo Finance
Boursorama
Affichage groupé
📁 Déjà dans vos portefeuilles
🌐 Yahoo Finance
📊 Boursorama
➕ Créer un nouveau support
Bonus
détection automatique des ISIN
debounce
annulation des requêtes obsolètes
📈 Graphique d’évolution
Le portefeuille affiche un graphique ECharts avec :

Valorisation
Capital investi
+/- value
Notes techniques
axe X en mode category
capital investi filtré pour exclure les arbitrages internes
historique reconstruit depuis les transactions
📋 Relevé annuel
Une popup permet d’afficher la situation exacte du portefeuille au 31/12 d’une année donnée.

Contenu
total versé
valorisation
+/- value
cash
valorisation des titres
détail des positions
séparation visuelle des réserves de liquidités
Accès
Depuis la section Positions, via l’icône 📄.

🔄 Scripts utiles
Migration BDD
Bash

python migrate.py
Permet notamment :

d’ajouter les colonnes enrichies de Transaction
de créer la table support_labels
Reset des données
Bash

python reset_data.py
Le reset :

supprime transactions, valorisations et positions classiques
préserve les Fonds €
remet leur quantité à 0
remet leur PRU à 1.0
✅ Fonctionnalités stables
 Gestion des membres
 Gestion de plusieurs portefeuilles
 Suivi des positions
 Cours actuels Yahoo + Boursorama
 Historique des cours Yahoo
 Reconstruction historique complète des valorisations
 Graphique d’évolution
 PRU automatique à l’achat / vente
 Arbitrages internes correctement gérés
 Capital investi exact
 Gestion des Fonds €
 Dividendes distribués et réinvestis
 Frais en euros et en parts
 Recherche unifiée à l’achat
 Backfill automatique après opérations impactantes
 Mode SQLite WAL + timeout
 Achats / ventes fractionnaires
 Relevé annuel détaillé
 Renommage personnalisé des supports
 Affichage des noms personnalisés dans positions / vente / transactions / relevé annuel
🟡 En cours / à améliorer
 Adaptation dynamique des dates selon le zoom du graphique
 Loader visuel pendant les backfills
 Petites améliorations UI / polish
⚠️ Limitations connues
Pas d’édition directe des achats / ventes
Pas d’édition directe des transactions de flux
SCPI non gérées correctement
Pas de gestion des splits / fractionnements d’actions
Pas d’authentification
Pas de multi-utilisateur
Pas de sauvegarde automatique de la BDD
Pas d’export PDF / Excel
Le renommage des supports est cosmétique uniquement
Incohérence historique entre catégories Fonds € et Fonds Euro
Doublon de fonction get_yahoo_price_at_date dans services/_yahoo.py
Performance du backfill perfectible sur gros historiques
🧠 Règles importantes / pièges évités
Ne pas utiliser threading.Thread avec NiceGUI
Ne pas utiliser xAxis.type = 'time' avec des strings ISO sur ECharts
Ne pas recalculer l’historique depuis les seules positions actuelles
Ne pas compter les arbitrages internes dans le capital investi
Ne pas créer de Cash artificiel en AV / PER
Ne pas lancer de double session SQLAlchemy imbriquée avant un backfill
Ne pas insérer de NaN / Inf dans cours_historique
Ne pas envoyer un ISIN pur ou un nom d’OPCVM à yfinance.history()
Ne pas forcer les quantités entières sur des supports que l’utilisateur veut acheter en fractionné
🛣️ Roadmap
Court terme
zoom dynamique du graphique
loader pendant les backfills
améliorations visuelles
Plus tard
édition réelle des achats / ventes
édition des transactions de flux
harmonisation Fonds € / Fonds Euro
nettoyage du doublon dans _yahoo.py
export PDF / Excel du relevé annuel
gestion des SCPI
gestion des splits
authentification
indicateurs avancés (TRI, volatilité, max drawdown, benchmark)
📌 Usage prévu
Pynvest est un projet personnel conçu pour un usage local privé de suivi patrimonial familial.

Il n’est pas destiné, à ce stade, à :

un usage multi-utilisateur
une exposition publique
un usage bancaire / réglementaire
👤 Auteur
Projet développé par Zinhodo68.

GitHub :

https://github.com/Zinhodo68/Pynvest