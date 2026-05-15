"""Script de migration de la base de données.

Utilisation :
    python migrate.py

Ajoute si nécessaire :
- les champs enrichis de la table transactions
- la table support_labels
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'patrimoine.db'


def table_exists(cursor, table_name):
    """Vérifie si une table existe déjà."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


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
    if not DB_PATH.exists():
        print(f'❌ Base introuvable : {DB_PATH}')
        return

    conn = sqlite3.connect(DB_PATH)

    try:
        cursor = conn.cursor()

        # ---------------------------------------------------------------------
        # Migration : table transactions
        # ---------------------------------------------------------------------
        if table_exists(cursor, 'transactions'):
            print('🔄 Vérification des colonnes de transactions...')

            columns_to_add = [
                ('ticker', 'TEXT'),
                ('code', 'TEXT'),
                ('nom_titre', 'TEXT'),
                ('categorie', 'TEXT'),
                ('quantite', 'REAL'),
                ('prix_unitaire', 'REAL'),
            ]

            for column_name, column_type in columns_to_add:
                add_column_if_missing(cursor, 'transactions', column_name, column_type)
        else:
            print("⚠️ Table 'transactions' absente, migration des colonnes ignorée.")

        # ---------------------------------------------------------------------
        # Migration : table support_labels
        # ---------------------------------------------------------------------
        print('\n🔄 Vérification de la table support_labels...')

        if not table_exists(cursor, 'support_labels'):
            cursor.execute("""
                CREATE TABLE support_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    code TEXT,
                    custom_name TEXT NOT NULL,
                    original_name TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT ck_support_labels_has_identifier
                        CHECK (ticker IS NOT NULL OR code IS NOT NULL)
                )
            """)
            print('   ✅ Table créée : support_labels')
        else:
            print('   ⏭️  Table déjà présente : support_labels')

        # Index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_support_labels_ticker
            ON support_labels (ticker)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_support_labels_code
            ON support_labels (code)
        """)
        print('   ✅ Index vérifiés : ix_support_labels_ticker, ix_support_labels_code')

        conn.commit()
        print('\n✅ Migration terminée avec succès.')

    except Exception as e:
        conn.rollback()
        print(f'\n❌ Erreur pendant la migration : {e}')
        raise

    finally:
        conn.close()


if __name__ == '__main__':
    migrate()