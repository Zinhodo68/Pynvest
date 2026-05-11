from database.db import get_session
from database.models import Portefeuille

with get_session() as session:
    p = session.get(Portefeuille, 1)
    print(f"Portefeuille: {p.type}")
    print()
    for t in sorted(p.transactions, key=lambda x: x.date_operation):
        print(f"  {t.date_operation} | {t.type_operation:12s} | {t.montant:>8.2f} € | {t.libelle}")