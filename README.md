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
Gérer plusieurs membres de la famille
Créer différents types de portefeuilles (PEA, AV, livrets, comptes-titres, PER...)
Suivre les positions (actions, ETF, OPCVM, SCPI, crypto, fonds €, cash)
Visualiser l'évolution du patrimoine dans le temps
Récupérer automatiquement les cours via Yahoo Finance et Boursorama
Usage local privé (pas multi-utilisateur, pas d'authentification pour le moment).
📁 Structure du projet
code
Code
Pynvest/
├── main.py                     # Point d'entrée NiceGUI
├── migrate.py                  # Script de migration BDD
├── reset_data.py               # Script de reset des données
├── database/
│   ├── db.py                   # Connexion SQLAlchemy + get_session()
│   └── models.py               # ORM (Membre, Portefeuille, Position, Transaction, Valorisation, CoursHistorique)
├── services/
│   ├── _boursorama.py          # Scraper cours OPCVM/SICAV (cours du jour uniquement)
│   ├── _yahoo.py               # API yfinance (cours actuel + historique)
│   ├── _state.py               # État applicatif (last_update_date)
│   ├── market_data.py          # Façade unifiée multi-sources
│   ├── quotes_updater.py       # MAJ des cours + déclenchement backfill
│   ├── backfill.py             # 🔄 REFONDU : reconstruction depuis transactions (gestion correcte Fonds Euro)
│   └── positions_data.py       # Helpers pour les positions
├── pages/
│   ├── dashboard/
│   ├── membres/
│   ├── portefeuilles/
│   ├── portefeuilles_data.py
│   ├── positions_data.py
│   └── portefeuille_detail/
│       ├── init.py             # Redirige vers _content.py
│       ├── _content.py         # Orchestrateur principal
│       ├── _header.py          # En-tête + bouton MAJ cours
│       ├── _stats.py           # Cartes KPI
│       ├── _chart.py           # Graphique ECharts d'évolution
│       ├── _positions.py       # Tableau des positions
│       ├── _transactions.py    # 🔄 ENRICHI : dialogue générique pour flux (versement, retrait, intérêts, dividendes, frais)
│       ├── _buy_dialog.py      # 🔄 ENRICHI : gère achat Action/ETF/OPCVM/Manuel, inclut arbitrage Fonds €
│       ├── _sell_dialog.py     # 🔄 ENRICHI : gère vente + arbitrage Fonds € pour AV/PER, remplit nouveaux champs
│       ├── _mono_support.py    # Vue spécifique livrets
│       └── _cash_helpers.py    # Helpers gestion du cash (impact_cash, ajuster_cash)
├── components/                 # Composants UI réutilisables
├── theme/                      # Thème sombre/clair
├── utils/
│   └── formatters.py           # format_money, format_percent, get_perf_color
└── uploads/                    # Logos uploadés
🗄️ Schéma de base de données
Modèles SQLAlchemy (database/models.py)
Membre, Portefeuille, Position, Valorisation, CoursHistorique
Inchangés vs version précédente.
Transaction (🔄 ENRICHI)
Champs existants : id, portefeuille_id, date_operation, type_operation, montant, libelle, parent_transaction_id
🆕 Champs pour traçabilité des opérations de titre ou de flux complexes :
ticker : ticker Yahoo (ex: 'MC.PA')
code : ISIN (pour OPCVM)
nom_titre : nom du titre (snapshot de l'actif concerné par l'opération : acheté, vendu, source du dividende, cible des frais en parts)
categorie : catégorie (snapshot)
quantite : quantité de titres ou de parts impliquées (pour achat/vente, dividende réinvesti, frais en parts)
prix_unitaire : prix unitaire au moment de l'opération (pour achat/vente, dividende réinvesti, frais en parts)
Tous les champs liés aux titres sont nullable. Ils sont remplis si type_operation est 'achat', 'vente', 'dividende' (en particulier réinvesti), ou 'frais' (en parts).
🏗️ Architecture clé : Position vs Transaction
Décision architecturale (Session 2) : approche C+ hybride
Concept	Source de vérité	Usage
État actuel (quantités, PRU, valeur du jour)	Position	Affichage des cartes, tableaux, KPIs
Historique (qui détenait quoi à quelle date)	Transaction	Backfill, graphique d'évolution
Avantage : pas de calcul lourd à chaque affichage, mais reconstruction historique exacte possible.
⚙️ Fonctionnement des composants clés
🔄 Mise à jour des cours (services/quotes_updater.py)
[Inchangé]
🏗️ Backfill (services/backfill.py)
backfill_cours_historique(portefeuille_id)
Source = transactions d'achat/vente (pas seulement positions actuelles)
Permet de récupérer l'historique même pour des titres déjà revendus
Pour chaque ticker Yahoo unique → téléchargement complet via yfinance.history()
Insertion dans CoursHistorique (sans doublons)
backfill_valorisations(portefeuille_id)
⚠️ Supprime toutes les valorisations existantes
Date de départ = première transaction
Pour chaque jour :
Rejoue toutes les transactions jusqu'à ce jour (cash + positions)
Maintient un dict positions_held : {ticker/code/nom: {quantité, PRU, ...}}
Amélioration : Le traitement des opérations de type 'versement'/'retrait'/'interets'/'frais' a été ajusté pour correctement créer/mettre à jour la quantite des positions de Fonds Euro ou autres actifs spécifiques dans positions_held lorsque nom_titre et quantite sont renseignés. Cela assure une valorisation historique exacte, notamment pour les portefeuilles de type Assurance-Vie/PER, et corrige l'ancienne surévaluation de 500€ dans le graphique.
Calcule valo_titres = Σ quantité × cours_du_jour
Calcule valo_totale = cash + valo_titres
Crée un snapshot Valorisation
Avantage : historique exact même avec achats/ventes successifs du même titre.
📈 Graphique d'évolution (pages/portefeuille_detail/_chart.py)
[Inchangé — fonctionne parfaitement]
🛒 Dialog d'achat (pages/portefeuille_detail/_buy_dialog.py)
3 modes : ACTION/ETF/CRYPTO, OPCVM/SICAV, MANUEL
PRU auto-rempli selon la date d'achat (Yahoo)
Logique AV/PER enrichie : l'achat utilise un Fonds € source existant (arbitrage). Impossible de créer un Fonds € via ce dialogue.
Remplit les champs Transaction : ticker, code, nom_titre, categorie, quantite, prix_unitaire.
💹 Dialog de vente (pages/portefeuille_detail/_sell_dialog.py)
Sélection d'une position existante
PRU auto-rempli selon la date de vente (Yahoo, basé sur la source de la position)
Détection automatique de la source (yahoo si ticker, boursorama si code, manual sinon)
Amélioration : Pour les portefeuilles de type Assurance-Vie et PER, le dialogue de vente propose désormais de choisir un Fonds Euro de destination pour le produit de la vente et les frais associés, au lieu de créditer un 'Cash' générique. Cela génère des transactions de 'vente' et de 'versement' (ou 'frais') liées, qui sont affectées directement à la position du Fonds Euro choisi, assurant ainsi une gestion fidèle des flux internes au contrat.
Remplit les champs Transaction : ticker, code, nom_titre, categorie, quantite, prix_unitaire.
➕ Dialogue de transaction générique (pages/portefeuille_detail/_transactions.py)
Gère les types d'opération suivants pour l'ajout :
Versement : ajoute au Cash ou Fonds € sélectionné.
Retrait : prélève du Cash ou Fonds € sélectionné.
Intérêts Fonds € : ajoute au Fonds € sélectionné (n'impacte pas le Total Versé).
Dividende :
Saisie du montant total OU dividende par part.
Choix de l'actif source.
Option "Réinvestir en parts" :
Si oui : calcul de la valeur monétaire des parts réinvesties (basé sur le cours actuel de l'actif). Met à jour la Position de l'actif (quantité et PRU).
Si non : ajoute le montant au Cash ou Fonds € sélectionné.
Le libellé de la transaction indique "Dividende (D)" pour distribué ou "Dividende (C)" pour capitalisé/réinvesti.
Pour les dividendes (C), le sous-texte de la transaction liste les parts et le prix unitaire.
Frais :
Choix du mode "Frais en euros" ou "Frais en parts".
Si "Frais en euros" : Saisie du montant en € et prélèvement du Cash ou Fonds € sélectionné.
Si "Frais en parts" : Choix de l'actif, saisie de la quantité à prélever (ou quantité finale), et prélèvement de la Position de l'actif (la valeur monétaire est calculée avec le cours actuel et stockée dans la transaction).
Remplit les champs Transaction : nom_titre, categorie, quantite, prix_unitaire pour la traçabilité des flux (intérêts, dividendes, frais en parts).
✅ Fonctionnalités déjà développées
🟢 Stable et testé
Gestion des membres
Création de portefeuilles (multi/mono-support)
Ajout de positions (Action/ETF, OPCVM, manuel)
Récupération des cours actuels (Yahoo + Boursorama)
Historique des cours via yfinance
Reconstruction exacte de l'historique de valorisation depuis les transactions (incluant la gestion améliorée des Fonds Euro pour les versements/retraits/intérêts/frais)
Graphique d'évolution multi-courbes
Format intelligent des dates de l'axe X
Gestion correcte des achats/ventes successifs du même titre dans le graphique
PRU auto-rempli selon date d'achat (Yahoo)
PRU auto-rempli selon date de vente (Yahoo)
Gestion des Fonds Euro :
Fonds Euro non créables manuellement via le dialogue d'achat de titre.
Arbitrage AV/PER : l'achat de titres prélève un Fonds € existant.
Versement/Retrait sur un Fonds € spécifique (pour AV/PER).
Saisie annuelle des intérêts des Fonds Euro (type_operation='interets').
Amélioration : Vente de titres dans AV/PER avec arbitrage automatique vers Fonds Euro sélectionné (gestion des flux et frais internes au contrat).
Gestion des Dividendes :
Saisie du dividende distribué en cash (type_operation='dividende', impacte Cash/Fonds €).
Saisie du dividende réinvesti en parts (type_operation='dividende', impacte la Position de l'actif).
Double saisie (montant total / par part) pour les dividendes distribués.
Affichage clair "Dividende (D)" / "Dividende (C)" dans la liste des transactions.
Affichage des détails (parts @ prix) pour les dividendes capitalisés dans la liste.
Gestion des Frais :
Saisie des frais en euros (type_operation='frais', impacte Cash/Fonds €).
Saisie des frais en parts (prélèvement de la Position d'un actif spécifique).
Double saisie (quantité à prélever / quantité finale) pour les frais en parts.
Affichage clair "Frais (en parts)" dans la liste des transactions avec les détails.
🟡 En cours / partiel
Adaptation des dates au zoom dynamique du graphique
🔴 Limitations connues / Non développé
❌ Édition directe des transactions de flux (versement, retrait, dividendes, intérêts, frais) non supportée. Pour modifier, veuillez supprimer la transaction et la recréer.
❌ SCPI non gérées correctement (système de revalorisation et distributions spécifiques).
❌ Pas de gestion des fractionnements d'actions.
❌ Pas d'authentification / multi-user.
❌ Pas de sauvegarde automatique de la BDD.
❌ Pas d'export PDF/Excel.
🎯 Roadmap Sessions
✅ Session 1 — Graphique d'évolution (terminée)
Problèmes résolus : crash threads, backfill bidon, date_creation None, valorisation incorrecte, cash non pris en compte, doublons d'années, PRU sans lien avec marché.
Ajouts : get_yahoo_history(), get_yahoo_price_at_date(), refonte backfill v1, format intelligent des dates, PRU auto à l'achat.
✅ Session 2 — Refonte historique (terminée)
Problèmes résolus : PRU auto à la vente (avec détection auto de la source), graphique cassé après vente.
Ajouts : 6 nouveaux champs dans Transaction, migration BDD via migrate.py, reset_data.py, _buy_dialog.py et _sell_dialog.py enrichis, backfill.py complètement refondu.
Décisions architecturales : Approche C+ hybride, modèle Transaction étendu mais nullable.
✅ Session 3 — Fonds €, Dividendes et Frais (terminée)
Problèmes résolus :
Gestion des Fonds Euro : Arbitrage AV/PER (achat de titres depuis Fonds €), versements/retraits sur Fonds €, impossibilité de créer manuellement un Fonds € via "Acheter un titre".
Saisie des intérêts annuels des Fonds Euro (type_operation='interets').
Gestion complète des Dividendes : distribués en cash (D) ou réinvestis en parts (C), double saisie montant total/par part.
Gestion des Frais : en euros (débit Cash/Fonds €) ou en parts d'actifs (débit Position d'un titre), double saisie quantité à prélever/quantité finale.
Affichage clair des types de dividendes (D/C) et des frais en parts dans la liste des transactions.
Correction de la valorisation du graphique : Le backfill gère désormais correctement l'initialisation et la mise à jour des positions de Fonds Euro lors des versements, retraits, intérêts et frais, assurant une valorisation historique exacte et cohérente.
Amélioration du dialogue de vente : Pour les portefeuilles AV/PER, la vente d'un titre propose désormais un Fonds Euro de destination pour le produit de la vente et les frais, avec génération de transactions liées et mise à jour directe des positions.
Ajouts : Logiques complexes dans _transactions.py, _buy_dialog.py et _sell_dialog.py, améliorations des validations et de la traçabilité.
🔜 Session 4 — Polish UI
Zoom dynamique du graphique
Indicateur de loading pendant backfill
Supprimer les points sur les courbes
Améliorations diverses
🔜 Plus tard
Export PDF/Excel
SCPI (système de revalorisation et distributions)
Splits/fractionnements
Authentification
Indicateurs avancés (TRI, volatilité, max drawdown)
Comparaison vs benchmark
🐛 Pièges connus / Anti-patterns à éviter
❌ Ne JAMAIS utiliser threading.Thread avec NiceGUI
Crash : RuntimeError: The current slot cannot be determined
✅ Utiliser await run.io_bound(...) ou asyncio.to_thread(...)
❌ ECharts.xAxis.type = 'time' avec strings ISO
Affiche des 01:00:01 partout
✅ Utiliser 'category' avec format manuel
❌ Les events update:model-value sur ui.input ne se déclenchent pas avec bind_value
✅ Écouter directement le composant source (ex: ui.date)
✅ Ou utiliser 'blur' sur l'input
❌ Portefeuille.date_creation = None casse silencieusement le backfill
✅ Le backfill utilise désormais la date de la première transaction
❌ Calculer l'historique uniquement depuis les positions actuelles
Si un titre a été vendu, la position n'existe plus → historique cassé
✅ Source = transactions (qui contiennent les nouveaux champs ticker/quantite/prix)