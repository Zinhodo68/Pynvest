import sqlite3
conn = sqlite3.connect('patrimoine.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT id, nom, quantite, prix_moyen, cours_actuel, updated_at
    FROM positions
    WHERE portefeuille_id = 10
    ORDER BY updated_at DESC
""")
for row in cur.fetchall():
    print(dict(row))
conn.close()