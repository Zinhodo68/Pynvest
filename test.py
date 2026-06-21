import sqlite3
conn = sqlite3.connect('patrimoine.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT id, portefeuille_id, nom, quantite
    FROM positions
    WHERE nom = 'Cash'
""")
rows = cur.fetchall()
for row in rows:
    print(dict(row))
conn.close()