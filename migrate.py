"""Script de migration de la base de données.

À lancer une fois pour ajouter les nouveaux champs à la table transactions.
Utilisation : python migrate.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'patrimoine.db'


def column_exists(cursor, table_name, column_name):
    """Vérifie si une colonne existe déjà dans une table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def add_column_if_missing(cursor, table_name, column_name, column_type):
    """Ajoute une colonne si elle n'existe pas déjà."""
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )
        print(f'   ✅ Colonne ajoutée : {table_name}.{column_name}')
    else:
        print(f'   ⏭️  Colonne déjà présente : {table_name}.{column_name}')


def migrate():
    """Lance la migration."""
    print(f'🔧 Migration de la base : {DB_PATH}')

    if not DB_PATH.exists():
        print(f'❌ Base introuvable : {DB_PATH}')
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    print()
    print('📋 Migration de la table transactions :')

    # Nouveaux champs pour le suivi historique des achats/ventes
    new_columns = [
        ('ticker', 'VARCHAR(50)'),
        ('code', 'VARCHAR(50)'),
        ('nom_titre', 'VARCHAR(200)'),
        ('categorie', 'VARCHAR(50)'),
        ('quantite', 'FLOAT'),
        ('prix_unitaire', 'FLOAT'),
    ]

    for col_name, col_type in new_columns:
        add_column_if_missing(cursor, 'transactions', col_name, col_type)

    conn.commit()
    conn.close()

    print()
    print('✅ Migration terminée avec succès !')


if __name__ == '__main__':
    migrate()