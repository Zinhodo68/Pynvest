"""Script pour supprimer toutes les transactions, positions et valorisations
d'un portefeuille (mais garder le portefeuille lui-même).

⚠️ ATTENTION : action destructive !
Utilisation : python reset_data.py
"""
from database.db import get_session
from database.models import Portefeuille, Position, Transaction, Valorisation, CoursHistorique
from sqlalchemy import select


def reset_portfolio_data():
    """Affiche les portefeuilles et permet de choisir lequel reset."""
    with get_session() as session:
        portefeuilles = session.execute(
            select(Portefeuille).order_by(Portefeuille.id)
        ).scalars().all()

        if not portefeuilles:
            print('Aucun portefeuille trouvé.')
            return

        print('\n📁 Portefeuilles existants :')
        for p in portefeuilles:
            nb_pos = len(p.positions)
            nb_tx = len(p.transactions)
            nb_valo = len(p.valorisations)
            print(f'   {p.id}: {p.nom_affiche} '
                  f'({nb_pos} positions, {nb_tx} transactions, {nb_valo} valorisations)')

        print()
        choice = input('ID du portefeuille à reset (ou "all" pour tous, "q" pour annuler) : ')

        if choice.lower() == 'q':
            print('Annulé.')
            return

        if choice.lower() == 'all':
            target_ids = [p.id for p in portefeuilles]
        else:
            try:
                target_ids = [int(choice)]
            except ValueError:
                print('❌ Choix invalide.')
                return

        confirm = input(f'⚠️  Supprimer toutes les données de {len(target_ids)} '
                        f'portefeuille(s) ? (tape "OUI" pour confirmer) : ')
        if confirm != 'OUI':
            print('Annulé.')
            return

        for pid in target_ids:
            p = session.get(Portefeuille, pid)
            if not p:
                continue

            nb_pos = len(p.positions)
            nb_tx = len(p.transactions)
            nb_valo = len(p.valorisations)

            # Suppression en cascade via les relations
            for pos in list(p.positions):
                session.delete(pos)
            for tx in list(p.transactions):
                session.delete(tx)
            for v in list(p.valorisations):
                session.delete(v)

            print(f'   ✅ Portefeuille {pid} : {nb_pos} positions, '
                  f'{nb_tx} transactions, {nb_valo} valorisations supprimées')

        # Optionnel : nettoyer aussi CoursHistorique
        clean_cours = input('\nSupprimer aussi tout l\'historique des cours ? (o/N) : ')
        if clean_cours.lower() == 'o':
            session.query(CoursHistorique).delete()
            print('   ✅ Historique des cours vidé')

        session.commit()

    print('\n✅ Reset terminé !')


if __name__ == '__main__':
    reset_portfolio_data()