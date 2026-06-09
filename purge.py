import sqlite3

# Connexion à la base
conn = sqlite3.connect('patrimoine.db')
cursor = conn.cursor()

# Vide la table cours_historique
cursor.execute("DELETE FROM cours_historique;")
print(f"Lignes supprimées de cours_historique: {cursor.rowcount}")

# Enregistre et ferme
conn.commit()
conn.close()