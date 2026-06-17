from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from database.models import Base, Position
from database.db import DATABASE_URL

print(f"Connecting to database: {DATABASE_URL}")
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)

def delete_independence_asset():
    with Session() as session:
        # Find the asset starting with "Indépendance"
        asset_to_delete = session.execute(
            select(Position).where(Position.nom.like("Indépendance%%"))
        ).scalar_one_or_none()

        if asset_to_delete:
            print(f"Deleting asset: {asset_to_delete.nom} (ID: {asset_to_delete.id})")
            session.delete(asset_to_delete)
            session.commit()
            print("Asset deleted successfully.")
        else:
            print("No asset found starting with 'Indépendance'.")

if __name__ == "__main__":
    delete_independence_asset()
