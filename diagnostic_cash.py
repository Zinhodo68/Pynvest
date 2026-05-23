# debug_pea_v3.py
from database.db import get_session, init_db
from database.models import Portefeuille

init_db()

PEA_ID = 2

with get_session() as session:
    p = session.get(Portefeuille, PEA_ID)

    print(f"=== {p.nom_affiche} (ID={p.id}) ===\n")

    # ── 1. Positions réelles en BDD ──
    print("--- POSITIONS EN BDD ---")
    bdd_positions = {}
    for pos in p.positions:
        key = pos.ticker or pos.code or pos.nom
        bdd_positions[key] = {
            'nom': pos.nom,
            'qte': pos.quantite,
            'cours': pos.cours_actuel or pos.prix_moyen or 0,
            'cat': pos.categorie,
        }
        print(f"  {pos.nom:45s} | key={key:20s} | qté={pos.quantite:12.4f} | cat={pos.categorie}")
    print()

    # ── 2. Rejouer toutes les transactions ──
    ARBITRAGE_CHILD_TYPES = {'achat', 'vente', 'versement', 'retrait'}
    transactions = sorted(p.transactions, key=lambda t: (t.date_operation, t.id))

    arbitrage_parent_ids = set()
    for t in transactions:
        if t.parent_transaction_id is not None and t.type_operation in ARBITRAGE_CHILD_TYPES:
            arbitrage_parent_ids.add(t.parent_transaction_id)

    cash = 0.0
    positions_held = {}

    for t in transactions:
        key = t.ticker or t.code or t.nom_titre
        is_asset_specific = bool(key and t.quantite is not None)
        is_arb_child = (t.parent_transaction_id is not None and t.type_operation in ARBITRAGE_CHILD_TYPES)
        is_arb_parent = t.id in arbitrage_parent_ids
        is_internal = is_arb_child or is_arb_parent

        if t.type_operation == 'versement':
            if is_asset_specific:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] += t.quantite
            else:
                if not is_internal:
                    cash += t.montant

        elif t.type_operation == 'retrait':
            if is_asset_specific:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] -= t.quantite
            else:
                if not is_internal:
                    cash -= t.montant

        elif t.type_operation == 'achat':
            if not is_internal:
                cash -= t.montant
            if t.quantite and key:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] += t.quantite

        elif t.type_operation == 'vente':
            if not is_internal:
                cash += t.montant
            if t.quantite and key:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] -= t.quantite

        elif t.type_operation == 'dividende':
            if is_asset_specific:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] += t.quantite
            else:
                cash += t.montant

        elif t.type_operation == 'frais':
            if is_asset_specific:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] -= t.quantite
            else:
                cash -= t.montant

        elif t.type_operation == 'interets':
            if is_asset_specific:
                positions_held.setdefault(key, {'qte': 0, 'nom': t.nom_titre, 'cat': t.categorie})
                positions_held[key]['qte'] += t.quantite
            else:
                cash += t.montant

    print("--- POSITIONS RECALCULÉES (transactions) ---")
    for key, info in sorted(positions_held.items()):
        if abs(info['qte']) > 0.0001:
            print(f"  {info['nom']:45s} | key={key:20s} | qté={info['qte']:12.4f} | cat={info.get('cat', '?')}")
    print(f"\n  Cash recalculé = {cash:12.2f}")
    print()

    # ── 3. Comparaison détaillée ──
    print("=" * 100)
    print("--- COMPARAISON POSITION PAR POSITION ---")
    print(f"  {'KEY':20s} | {'NOM':35s} | {'BDD qté':>12s} | {'CALC qté':>12s} | {'ÉCART':>12s} | STATUT")
    print("-" * 100)

    all_keys = set(bdd_positions.keys()) | set(k for k, v in positions_held.items() if abs(v['qte']) > 0.0001)

    total_ecart_valo = 0
    for key in sorted(all_keys):
        bdd = bdd_positions.get(key)
        calc = positions_held.get(key)

        bdd_qte = bdd['qte'] if bdd else 0
        calc_qte = calc['qte'] if calc else 0
        ecart = calc_qte - bdd_qte
        nom = (bdd or calc or {}).get('nom', key)

        if abs(ecart) < 0.0001:
            statut = "✅ OK"
        else:
            statut = "❌ ÉCART"

        print(f"  {key:20s} | {nom:35s} | {bdd_qte:12.4f} | {calc_qte:12.4f} | {ecart:12.4f} | {statut}")

        # Calculer l'impact en € de l'écart
        if abs(ecart) > 0.0001:
            cours = bdd['cours'] if bdd else (calc.get('pru', 0) if calc else 0)
            impact = ecart * cours if cours else 0
            total_ecart_valo += impact
            print(f"  {'':20s} | {'':35s} | {'':12s} | {'':12s} | impact = {impact:10.2f} €")

    # Cash
    cash_bdd = bdd_positions.get('Cash', {}).get('qte', 0)
    ecart_cash = cash - cash_bdd
    statut_cash = "✅ OK" if abs(ecart_cash) < 0.01 else "❌ ÉCART"
    print(f"  {'CASH':20s} | {'Cash résiduel':35s} | {cash_bdd:12.2f} | {cash:12.2f} | {ecart_cash:12.2f} | {statut_cash}")

    print("-" * 100)
    print(f"\n  Écart total valorisation (hors cash) = {total_ecart_valo:12.2f} €")
    print(f"  Écart cash                           = {ecart_cash:12.2f} €")
    print(f"  Écart total                          = {total_ecart_valo + ecart_cash:12.2f} €")