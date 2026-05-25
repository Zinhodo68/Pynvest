import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database.models import Position, Transaction

DB_PATH = Path(__file__).parent / 'patrimoine.db'
engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)

DRY_RUN = False   # passe à False pour appliquer

with SessionLocal() as session:
    positions = session.execute(
        select(Position).where(
            Position.quantite > 0,
            Position.nom != 'Cash',
            Position.categorie.notin_(['Fonds Euro', 'Fonds €']),
        )
    ).scalars().all()

    nb_corriges = 0

    for pos in positions:
        # On récupère toutes les transactions de ce titre dans ce portefeuille
        txs = session.execute(
            select(Transaction).where(
                Transaction.portefeuille_id == pos.portefeuille_id,
                Transaction.type_operation.in_(['achat', 'vente']),
            ).order_by(Transaction.date_operation, Transaction.id)
        ).scalars().all()

        # Match strict
        def match(t):
            if pos.ticker and t.ticker == pos.ticker:
                return True
            if pos.code and t.code == pos.code:
                return True
            return t.nom_titre == pos.nom

        txs = [t for t in txs if match(t)]
        if not txs:
            continue

        qte = 0.0
        pru = 0.0
        for t in txs:
            if t.quantite is None or t.prix_unitaire is None:
                continue
            if t.type_operation == 'achat':
                new_qte = qte + t.quantite
                if new_qte <= 0:
                    qte = 0
                    pru = 0
                else:
                    pru = (qte * pru + t.quantite * t.prix_unitaire) / new_qte
                    qte = new_qte
            elif t.type_operation == 'vente':
                qte -= t.quantite
                if qte <= 1e-9:
                    qte = 0
                    pru = 0

        if qte <= 0:
            continue

        if abs(qte - (pos.quantite or 0)) > 0.001:
            print(f'  ⚠️ qte différente pour {pos.nom} : BDD={pos.quantite} calc={qte}')

        if abs(pru - (pos.prix_moyen or 0)) > 0.01:
            print(f'  🔧 {pos.nom:<30} ticker={pos.ticker:<10} '
                  f'PRU BDD={pos.prix_moyen:>10.4f} -> calc={pru:>10.4f}')
            if not DRY_RUN:
                pos.prix_moyen = pru
            nb_corriges += 1

    if not DRY_RUN:
        session.commit()
        print(f'\n✅ {nb_corriges} positions corrigées')
    else:
        print(f'\n[DRY RUN] {nb_corriges} positions à corriger '
              f'(passe DRY_RUN=False pour appliquer)')