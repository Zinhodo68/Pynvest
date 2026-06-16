import sqlite3

# Connexion à votre base (le nom du fichier vu sur votre capture)
conn = sqlite3.connect('patrimoine.db')
cursor = conn.cursor()

try:
    # 1. Vérification
    print("--- Vérification avant correction ---")
    cursor.execute("SELECT id, nom, ticker, code FROM positions WHERE nom LIKE '%Indépendance%'")
    for row in cursor.fetchall():
        print(row)

    # 2. Application des corrections
    print("\n--- Application des corrections... ---")

    queries = [
        "UPDATE positions SET code = COALESCE(code, ticker), ticker = NULL WHERE nom LIKE '%Indépendance AM Europe Small%' AND ticker LIKE 'FR%';",
        "UPDATE transactions SET code = COALESCE(code, ticker), ticker = NULL WHERE nom_titre LIKE '%Indépendance AM Europe Small%' AND ticker LIKE 'FR%';",
        "UPDATE cours_historique SET isin = COALESCE(isin, ticker), ticker = NULL WHERE ticker LIKE 'FR%' AND length(ticker) = 12;"
    ]

    for q in queries:
        cursor.execute(q)

    conn.commit()
    print("Corrections enregistrées avec succès.")

    # 3. Vérification finale
    print("\n--- Vérification après correction ---")
    cursor.execute("SELECT id, nom, ticker, code FROM positions WHERE nom LIKE '%Indépendance%'")
    for row in cursor.fetchall():
        print(row)

except Exception as e:
    print(f"Erreur : {e}")
finally:
    conn.close()