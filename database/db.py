from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# SQLite local (fichier patrimoine.db à la racine du projet)
DB_PATH = Path(__file__).parent.parent / 'patrimoine.db'
DATABASE_URL = f'sqlite:///{DB_PATH}'

# Pour migrer plus tard vers Supabase, tu remplaces juste cette ligne par :
# DATABASE_URL = 'postgresql://user:pass@host:5432/dbname'

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={
        'check_same_thread': False,
        'timeout': 30,  # 🆕 Attendre jusqu'à 30s avant de lever 'database is locked'
    },
)


# 🆕 Activer le mode WAL (Write-Ahead Logging) pour SQLite
# Avantages :
#   - Plusieurs lecteurs + 1 écrivain peuvent travailler en parallèle
#   - Évite la majorité des erreurs "database is locked"
#   - Recommandé pour les apps mono-utilisateur avec beaucoup d'I/O
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Active WAL et optimise SQLite à chaque nouvelle connexion."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")        # mode Write-Ahead Logging
    cursor.execute("PRAGMA synchronous=NORMAL")      # bon compromis perf/sécurité
    cursor.execute("PRAGMA busy_timeout=30000")      # 30s d'attente avant erreur
    cursor.execute("PRAGMA foreign_keys=ON")         # contrôle d'intégrité référentielle
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_session():
    """Retourne une nouvelle session SQLAlchemy."""
    return SessionLocal()


def init_db():
    """Crée toutes les tables qui n'existent pas encore (sans toucher aux existantes)."""
    from database import models  # important : charge tous les modèles
    Base.metadata.create_all(bind=engine)  # ne recrée pas si la table existe déjà


def get_all_membres():
    """Retourne tous les membres sous forme de dictionnaires."""
    from database.models import Membre
    from sqlalchemy import select
    with get_session() as session:
        membres = session.execute(select(Membre).order_by(Membre.id)).scalars().all()
        return [m.to_dict() for m in membres]


def get_all_portefeuilles():
    """Retourne tous les portefeuilles avec infos du propriétaire."""
    from database.models import Portefeuille
    from sqlalchemy import select
    with get_session() as session:
        portefeuilles = session.execute(
            select(Portefeuille).order_by(Portefeuille.id)
        ).scalars().all()
        return [p.to_dict() for p in portefeuilles]


def get_portefeuilles_by_membre(membre_id: int):
    """Retourne les portefeuilles d'un membre spécifique."""
    from database.models import Portefeuille
    from sqlalchemy import select
    with get_session() as session:
        portefeuilles = session.execute(
            select(Portefeuille).where(Portefeuille.proprietaire_id == membre_id)
        ).scalars().all()
        return [p.to_dict() for p in portefeuilles]