from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker, declarative_base, selectinload
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
        'timeout': 30,
    },
)

# Activer le mode WAL (Write-Ahead Logging) pour SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Active WAL et optimise SQLite à chaque nouvelle connexion."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_session():
    """Retourne une nouvelle session SQLAlchemy."""
    return SessionLocal()


def init_db():
    """Crée toutes les tables qui n'existent pas encore."""
    from database import models
    Base.metadata.create_all(bind=engine)


# ══════════════════════════════════════════════════════════════════════════
# Fonctions de lecture — avec preload_stats() pour éviter N+1 queries
# ══════════════════════════════════════════════════════════════════════════

def get_all_membres():
    """Retourne tous les membres sous forme de dictionnaires."""
    from database.models import Membre
    with get_session() as session:
        membres = session.execute(select(Membre).order_by(Membre.id)).scalars().all()
        return [m.to_dict() for m in membres]


def get_all_portefeuilles():
    """Retourne tous les portefeuilles avec stats pré-calculées.

    ⚡ 1 requête SQL agrégée au lieu de ~4N lazy-loads.
    """
    from database.models import Portefeuille
    from services.portfolio_stats import preload_stats

    with get_session() as session:
        portefeuilles = session.execute(
            select(Portefeuille)
            .options(selectinload(Portefeuille.proprietaire))  # eager load membre
            .order_by(Portefeuille.id)
        ).scalars().all()

        preload_stats(session, portefeuilles)
        return [p.to_dict() for p in portefeuilles]


def get_portefeuilles_by_membre(membre_id: int):
    """Retourne les portefeuilles d'un membre avec stats pré-calculées.

    ⚡ 1 requête SQL agrégée au lieu de ~4N lazy-loads.
    """
    from database.models import Portefeuille
    from services.portfolio_stats import preload_stats

    with get_session() as session:
        portefeuilles = session.execute(
            select(Portefeuille)
            .options(selectinload(Portefeuille.proprietaire))
            .where(Portefeuille.proprietaire_id == membre_id)
            .order_by(Portefeuille.id)
        ).scalars().all()

        preload_stats(session, portefeuilles)
        return [p.to_dict() for p in portefeuilles]
