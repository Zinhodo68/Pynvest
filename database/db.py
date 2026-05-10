from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path

# SQLite local (fichier patrimoine.db à la racine du projet)
DB_PATH = Path(__file__).parent.parent / 'patrimoine.db'
DATABASE_URL = f'sqlite:///{DB_PATH}'

# Pour migrer plus tard vers Supabase, tu remplaces juste cette ligne par :
# DATABASE_URL = 'postgresql://user:pass@host:5432/dbname'

engine = create_engine(DATABASE_URL, echo=False, connect_args={'check_same_thread': False})
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