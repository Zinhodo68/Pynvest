# 📊 PYNVEST — Documentation projet pour reprise rapide

> **Document de contexte** pour Claude (ou autre IA) — permet une mise à jour rapide de la compréhension du projet en début de session.

---

## 🔗 Liens & Accès

- **GitHub (public)** : https://github.com/Zinhodo68/Pynvest
- **Propriétaire** : Zinhodo68
- **Stack** : Python 3.14 + NiceGUI + SQLAlchemy + SQLite + ECharts
- **IDE utilisé** : PyCharm sous Windows
- **Environnement** : `.venv` dans `C:\Users\liogi\PycharmProjects\Projects\.venv`

---

## 🎯 Objectif du projet

**Pynvest** est une **webapp personnelle** de gestion du patrimoine financier familial. Elle permet de :
- Gérer plusieurs membres de la famille
- Créer différents types de portefeuilles (PEA, AV, livrets, comptes-titres, PER...)
- Suivre les positions (actions, ETF, OPCVM, SCPI, crypto, fonds €, cash)
- Visualiser l'évolution du patrimoine dans le temps
- Récupérer automatiquement les cours via Yahoo Finance et Boursorama

Usage **local privé** (pas multi-utilisateur, pas d'authentification pour le moment).

---

## 📁 Structure du projet
Pynvest/
├── main.py # Point d'entrée NiceGUI
├── migrate.py # 🆕 Script de migration BDD
├── reset_data.py # 🆕 Script de reset des données
├── database/
│ ├── db.py # Connexion SQLAlchemy + get_session()
│ └── models.py # ORM (Membre, Portefeuille, Position, Transaction, Valorisation, CoursHistorique)
├── services/
│ ├── _boursorama.py # Scraper cours OPCVM/SICAV (cours du jour uniquement)
│ ├── _yahoo.py # API yfinance (cours actuel + historique)
│ ├── _state.py # État applicatif (last_update_date)
│ ├── market_data.py # Façade unifiée multi-sources
│ ├── quotes_updater.py # MAJ des cours + déclenchement backfill
│ ├── backfill.py # 🔄 REFONDU : reconstruction depuis transactions
│ └── positions_data.py # Helpers pour les positions
├── pages/
│ ├── dashboard/
│ ├── membres/
│ ├── portefeuilles/
│ ├── portefeuilles_data.py
│ ├── positions_data.py
│ └── portefeuille_detail/
│ ├── init.py # Redirige vers _content.py
│ ├── _content.py # Orchestrateur principal
│ ├── _header.py # En-tête + bouton MAJ cours
│ ├── _stats.py # Cartes KPI
│ ├── _chart.py # Graphique ECharts d'évolution
│ ├── _positions.py # Tableau des positions
│ ├── _transactions.py # Tableau des transactions
│ ├── _buy_dialog.py # 🔄 ENRICHI : remplit nouveaux champs
│ ├── _sell_dialog.py # 🔄 ENRICHI : remplit nouveaux champs
│ ├── _mono_support.py # Vue spécifique livrets
│ └── _cash_helpers.py # Helpers gestion du cash
├── components/ # Composants UI réutilisables
├── theme/ # Thème sombre/clair
├── utils/
│ └── formatters.py # format_money, format_percent, get_perf_color
└── uploads/ # Logos uploadés

text


---

## 🗄️ Schéma de base de données

### Modèles SQLAlchemy (`database/models.py`)

#### `Membre`, `Portefeuille`, `Position`, `Valorisation`, `CoursHistorique`
Inchangés vs version précédente.

#### `Transaction` (🔄 REFONDU)
- Champs existants : `id`, `portefeuille_id`, `date_operation`, `type_operation`, `montant`, `libelle`, `parent_transaction_id`
- 🆕 **Nouveaux champs (pour traçabilité historique des achats/ventes)** :
  - `ticker` : ticker Yahoo (ex: 'MC.PA')
  - `code` : ISIN (pour OPCVM)
  - `nom_titre` : nom du titre (snapshot)
  - `categorie` : catégorie (snapshot)
  - `quantite` : quantité achetée/vendue
  - `prix_unitaire` : prix unitaire au moment de l'opération
- Tous les nouveaux champs sont **nullable** (versement/retrait/frais ne les remplissent pas)

---

## 🏗️ Architecture clé : Position vs Transaction

**Décision architecturale (Session 2)** : approche **C+ hybride**

| Concept | Source de vérité | Usage |
|---------|------------------|-------|
| **État actuel** (quantités, PRU, valeur du jour) | `Position` | Affichage des cartes, tableaux, KPIs |
| **Historique** (qui détenait quoi à quelle date) | `Transaction` | Backfill, graphique d'évolution |

**Avantage** : pas de calcul lourd à chaque affichage, mais reconstruction historique exacte possible.

---

## ⚙️ Fonctionnement des composants clés

### 🔄 Mise à jour des cours (`services/quotes_updater.py`)
[Inchangé]

### 🏗️ Backfill (`services/backfill.py`) 🔄 REFONDU
**`backfill_cours_historique(portefeuille_id)`**
- Source = **transactions d'achat/vente** (pas seulement positions actuelles)
- Permet de récupérer l'historique même pour des titres déjà revendus
- Pour chaque ticker Yahoo unique → téléchargement complet via `yfinance.history()`
- Insertion dans `CoursHistorique` (sans doublons)

**`backfill_valorisations(portefeuille_id)`**
- ⚠️ Supprime toutes les valorisations existantes
- Date de départ = **première transaction**
- Pour chaque jour :
  - Rejoue toutes les transactions jusqu'à ce jour (cash + positions)
  - Maintient un dict `positions_held` : {ticker/code/nom: {quantité, PRU, ...}}
  - Calcule `valo_titres = Σ quantité × cours_du_jour`
  - Calcule `valo_totale = cash + valo_titres`
  - Crée un snapshot `Valorisation`

**Avantage** : historique exact même avec achats/ventes successifs du même titre.

### 📈 Graphique d'évolution (`pages/portefeuille_detail/_chart.py`)
[Inchangé — fonctionne parfaitement]

### 🛒 Dialog d'achat (`pages/portefeuille_detail/_buy_dialog.py`)
- 3 modes : ACTION/ETF/CRYPTO, OPCVM/SICAV, MANUEL
- **PRU auto-rempli** selon la date d'achat (Yahoo)
- **🆕 Remplit les nouveaux champs Transaction** : ticker, code, nom_titre, categorie, quantite, prix_unitaire

### 💹 Dialog de vente (`pages/portefeuille_detail/_sell_dialog.py`)
- Sélection d'une position existante
- **PRU auto-rempli** selon la date de vente (Yahoo, basé sur la source de la position)
- Détection automatique de la source (yahoo si ticker, boursorama si code, manual sinon)
- **🆕 Remplit les nouveaux champs Transaction** : ticker, code, nom_titre, categorie, quantite, prix_unitaire

---

## ✅ Fonctionnalités déjà développées

### 🟢 Stable et testé
- [x] Gestion des membres
- [x] Création de portefeuilles (multi/mono-support)
- [x] Ajout de positions (Action/ETF, OPCVM, manuel)
- [x] Saisie des transactions (versement, retrait, achat, vente, frais)
- [x] Calcul automatique du cash
- [x] Récupération des cours actuels (Yahoo + Boursorama)
- [x] Historique des cours via yfinance
- [x] **🆕 Reconstruction exacte de l'historique de valorisation depuis les transactions**
- [x] Graphique d'évolution multi-courbes
- [x] PRU auto-rempli selon date d'achat (Yahoo)
- [x] PRU auto-rempli selon date de vente (Yahoo)
- [x] Format intelligent des dates de l'axe X
- [x] **🆕 Gestion correcte des achats/ventes successifs du même titre dans le graphique**

### 🟡 En cours / partiel
- [ ] Adaptation des dates au zoom dynamique du graphique

### 🔴 Limitations connues / Non développé
- ❌ Pas d'historique pour les OPCVM (Boursorama scrape uniquement le cours du jour)
- ❌ **Fonds € non gérés** (Session 3 prévue)
- ❌ **SCPI non gérées correctement** (Session 3 prévue)
- ❌ Pas de gestion des dividendes
- ❌ Pas de gestion des fractionnements d'actions
- ❌ Pas d'authentification / multi-user
- ❌ Pas de sauvegarde automatique de la BDD
- ❌ Pas d'export PDF/Excel

---

## 🎯 Roadmap Sessions

### ✅ Session 1 — Graphique d'évolution (terminée)
- Crash NiceGUI sur threads
- Backfill bidon
- date_creation = None
- PRU auto à l'achat
- Format intelligent des dates

### ✅ Session 2 — Refonte historique (terminée)
- PRU auto à la vente
- Refonte du modèle Transaction (6 nouveaux champs)
- Migration BDD via `migrate.py`
- Refonte complète du backfill
- **Résultat** : graphique exact même avec achats/ventes

### 🔜 Session 3 — Fonds € et SCPI (prévue)
**Décisions validées :**
- **Fonds €** : Option B (saisie réelle des intérêts annuels)
  - Nouveau type de transaction : `interets`
  - Modélisation avec saisie annuelle
  - Cas important : plusieurs fonds € dans un même portefeuille (ex: 30% Fond A + 20% Fond B + 50% UC)
- **SCPI** : actualisation via événements (achat, distribution, vente)
  - Stockage des revalorisations dans `CoursHistorique`
  - Saisie manuelle par l'utilisateur

### 🔜 Session 4 — Polish UI
- Zoom dynamique du graphique
- Indicateur de loading pendant backfill
- Améliorations diverses

### 🔜 Plus tard
- Export PDF/Excel
- Dividendes et coupons
- Splits/fractionnements
- Authentification
- Indicateurs avancés (TRI, volatilité, max drawdown)
- Comparaison vs benchmark

---

## 🐛 Pièges connus / Anti-patterns à éviter

1. **❌ Ne JAMAIS utiliser `threading.Thread` avec NiceGUI**
   - Crash : `RuntimeError: The current slot cannot be determined`
   - ✅ Utiliser `await run.io_bound(...)` ou `asyncio.to_thread(...)`

2. **❌ `ECharts.xAxis.type = 'time'` avec strings ISO**
   - Affiche des `01:00:01` partout
   - ✅ Utiliser `'category'` avec format manuel

3. **❌ Les events `update:model-value` sur `ui.input` ne se déclenchent pas avec `bind_value`**
   - ✅ Écouter directement le composant source (ex: `ui.date`)
   - ✅ Ou utiliser `'blur'` sur l'input

4. **❌ `Portefeuille.date_creation = None` casse silencieusement le backfill**
   - ✅ Le backfill utilise désormais la date de la première transaction

5. **❌ Calculer l'historique uniquement depuis les positions actuelles**
   - Si un titre a été vendu, la position n'existe plus → historique cassé
   - ✅ **Source = transactions** (qui contiennent les nouveaux champs ticker/quantite/prix)

---

## 🧪 Snippet de debug utile

```python
# test.py (à la racine)
from database.db import get_session
from database.models import Portefeuille

with get_session() as session:
    p = session.get(Portefeuille, 1)
    print(f"Portefeuille: {p.type}")
    print(f"Date création: {p.date_creation}")
    print()
    print("Positions:")
    for pos in p.positions:
        print(f"  📊 {pos.nom}")
        print(f"     ticker={pos.ticker!r}, code={pos.code!r}, categorie={pos.categorie!r}")
        print(f"     quantite={pos.quantite}, prix_moyen={pos.prix_moyen}, cours_actuel={pos.cours_actuel}")
        print(f"     date_ouverture={pos.date_ouverture}")
    print()
    print("Transactions:")
    for t in sorted(p.transactions, key=lambda x: x.date_operation):
        details = ''
        if t.ticker or t.quantite:
            details = f' | {t.ticker or t.code or ""} qte={t.quantite} pu={t.prix_unitaire}'
        print(f"  {t.date_operation} | {t.type_operation:12s} | {t.montant:>8.2f} € | {t.libelle or ''}{details}")

)
📝 Historique des sessions
Session 1 (J-1) — Graphique d'évolution
Problèmes résolus : crash threads, backfill bidon, date_creation None, valorisation incorrecte, cash non pris en compte, doublons d'années, PRU sans lien avec marché.
Ajouts : get_yahoo_history(), get_yahoo_price_at_date(), refonte backfill v1, format intelligent des dates, PRU auto à l'achat.

Session 2 (J) — Refonte historique
Problèmes résolus :
PRU auto à la vente (avec détection auto de la source)
Graphique cassé après vente (positions supprimées de la BDD)
Architecture limitée : Transaction ne stockait pas les détails
Ajouts :

6 nouveaux champs dans Transaction : ticker, code, nom_titre, categorie, quantite, prix_unitaire
migrate.py : script de migration manuelle des colonnes
reset_data.py : script de reset propre par portefeuille
_buy_dialog.py et _sell_dialog.py enrichis
backfill.py complètement refondu : reconstruction depuis transactions
Décisions architecturales :

Approche C+ hybride : Position = état actuel, Transaction = historique
Modèle Transaction étendu mais nullable pour rester compatible avec versement/retrait/frais


Session 3 (J) — Ajout des fond €(début)
Problèmes résolus : A la création d'une Assurance-Vie (AV) ou d'un PER (2 seuls uniques portefeuilles a avoir des Assurances-Vie)
on mentionne le ou les fond € qui seront utilisés dans le portefeuille.

Quand on fait un versement sur un portfeuille de type AV ou PER, on verse directement sur le fond € si il y en a 1 ou 1 des 2 AV si il y en a 2

TODO suite - Session 3 :
Retirer la possibilité de créer un "Fonds Euro" manuellement via la transaction de type "Acheter un titre" puisque ça sera géré à la racine du portefeuille. Dans le cadre PER ou AV, 'Achat servira uniquement à arbitrer l'argent des Fonds € vers des ETF/OPCVM
Gestion des interets des AV
Système de revalorisation pour SCPI

On a commencé a travailler dessus en répondant aux questions suivantes permettant d'orienter le code:

Q - Workflow de saisie des intérêts annuels - ton assureur t'annonce que ton fonds € a fait +2,5% sur l'année 2025. Comment tu veux le saisir ?
R - On saisie en € en fin d'année

Q - Date de versement des intérêts ?
R - Date par défaut = 31/12 de l'année concernée, modifiable

Q - Saisie des SCPI
Pour les SCPI, la distribution se fait en general en €sur le fond €.
Pour les ETF et les OPCVM ,ca depend si ils sont capitalisant ou distribuant. Il faut donc pouvoir savoir les interets en €(ca va sur le fond €) ou en parts (ca va augmenter le nb de parts du support).
LEs frais sur ces supports peuvent egalement etre en € ou en parts (retirées du nb de parts possedées)

proposition de scope pour cette session
Vu la complexité, je propose de séparer en sous-sessions :

Session 3a — 
Type de transaction interets (saisie en €)
Saisie annuelle des intérêts
Backfill qui en tient compte
Test sur un portefeuille AV simple
Session 3b (plus tard) — SCPI + Distributions
Nouvelle catégorie 'SCPI' (si pas déjà gérée)
Type de transaction distribution_eur
Logique : "destinataire fonds €" (Option C avec fonds € par défaut)
Saisie manuelle des revalorisations SCPI
Session 3c (encore plus tard) — Distributions/frais en parts
Type de transaction distribution_parts et frais_parts
Logique d'impact sur quantité/PRU
Tests OPCVM/ETF distribuants





💡 Tips pour les futures sessions
Pour Claude (ou IA) :
Toujours commencer par lire le repo GitHub (public) au lieu de demander à l'utilisateur
Vérifier les hypothèses avant de coder (lancer un snippet de debug si possible)
Ne pas inventer de noms de fichiers/fonctions — explorer la structure réelle
Demander des captures d'écran quand il y a un problème visuel
Faire des modifications minimales sur les fichiers existants (préserver le style)
Donner systématiquement les fichiers complets (ou des fonctions complètes), pas des patches partiels
Pour Lionel :
Faire un commit Git avant chaque session importante
Avoir le snippet de debug test.py sous la main
Décrire le bug avec : (1) ce que tu vois, (2) ce que tu attendais, (3) capture si visuel
Préciser le contexte métier dès le début (types d'actifs, sources de données...)
Document généré le : 2026-05-12
Dernière session : Session 2 — Refonte historique
Version document : 2.0

