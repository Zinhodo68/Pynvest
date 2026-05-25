import sys
from pathlib import Path

# Ajoute le projet au path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, or_, select, text
from sqlalchemy.orm import sessionmaker

DB_PATH = Path(__file__).parent / 'patrimoine.db'
DATABASE_URL = f'sqlite:///{DB_PATH}'

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine)

with SessionLocal() as session:

    print('\n' + '='*60)
    print('=== POSITIONS BUZZI ===')
    print('='*60)

    rows = session.execute(text("""
        SELECT id, portefeuille_id, nom, ticker, code, 
               quantite, prix_moyen, categorie, cours_actuel
        FROM positions
        WHERE UPPER(nom) LIKE '%BUZZI%' 
           OR UPPER(ticker) LIKE '%BUZZI%'
           OR UPPER(code) LIKE '%BUZZI%'
    """)).fetchall()

    if not rows:
        print('Aucune position BUZZI trouvée.')
    for r in rows:
        print(f"""
  id              = {r[0]}
  portefeuille_id = {r[1]}
  nom             = {r[2]}
  ticker          = {r[3]}
  code            = {r[4]}
  quantite        = {r[5]}
  prix_moyen      = {r[6]}
  categorie       = {r[7]}
  cours_actuel    = {r[8]}
""")

    print('\n' + '='*60)
    print('=== TRANSACTIONS BUZZI ===')
    print('='*60)

    rows = session.execute(text("""
        SELECT id, portefeuille_id, date_operation, type_operation,
               nom_titre, ticker, code, quantite, prix_unitaire, montant
        FROM transactions
        WHERE UPPER(nom_titre) LIKE '%BUZZI%'
           OR UPPER(ticker) LIKE '%BUZZI%'
           OR UPPER(code) LIKE '%BUZZI%'
        ORDER BY date_operation, id
    """)).fetchall()

    if not rows:
        print('Aucune transaction BUZZI trouvée.')
    for r in rows:
        print(f"""
  id              = {r[0]}
  portefeuille_id = {r[1]}
  date_operation  = {r[2]}
  type_operation  = {r[3]}
  nom_titre       = {r[4]}
  ticker          = {r[5]}
  code            = {r[6]}
  quantite        = {r[7]}
  prix_unitaire   = {r[8]}
  montant         = {r[9]}
""")