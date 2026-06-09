import sqlite3
import os

# 1. Connexion à la base
conn = sqlite3.connect('patrimoine.db')
cursor = conn.cursor()

print("--- Nettoyage de la base ---")

# 2. Suppression dans les différentes tables
cursor.execute("DELETE FROM transactions WHERE date_operation < '2017-01-01'")
print(f"Lignes supprimées dans transactions : {cursor.rowcount}")

cursor.execute("DELETE FROM cours_historique WHERE date_cours < '2017-01-01'")
print(f"Lignes supprimées dans cours_historique : {cursor.rowcount}")

cursor.execute("DELETE FROM valorisations WHERE date_valeur < '2017-01-01'")
print(f"Lignes supprimées dans valorisations : {cursor.rowcount}")

# Sauvegarder les suppressions
conn.commit()

taille_avant = os.path.getsize('patrimoine.db') / (1024 * 1024)
print(f"\nTaille avant compression : {taille_avant:.2f} Mo")

# 3. Compression de la base pour libérer l'espace disque (doit se faire hors transaction)
conn.isolation_level = None
conn.execute("VACUUM")
conn.isolation_level = ''

taille_apres = os.path.getsize('patrimoine.db') / (1024 * 1024)
print(f"Taille après compression : {taille_apres:.2f} Mo")

conn.close()