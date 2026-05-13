"""Script pour supprimer toutes les transactions, positions et valorisations
d'un portefeuille (mais garder le portefeuille lui-même et ses Fonds €).

⚠️ ATTENTION : action destructive !
Utilisation : python reset_data.py

Comportement :
- Supprime toutes les transactions, valorisations et positions classiques
- 🛡️ PRÉSERVE les positions de catégorie 'Fonds €' / 'Fonds Euro'
  (créées à la création des portefeuilles AV/PER)
- Réinitialise leur quantité à 0 et leur PRU à 1.0
- Optionnel : nettoyer l'historique des cours
"""
from database.db import get_session
from database.models import Portefeuille, Position, Transaction, Valorisation, CoursHistorique
from sqlalchemy import select

# 🛡️ Catégories à préserver lors d'un reset
RESERVES_CATEGORIES = ('Fonds €', 'Fonds Euro')


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
            nb_fonds_euro = sum(
                1 for pos in p.positions
                if pos.categorie in RESERVES_CATEGORIES
            )
            nb_tx = len(p.transactions)
            nb_valo = len(p.valorisations)
            fe_info = f', dont {nb_fonds_euro} Fonds €' if nb_fonds_euro else ''
            print(f'   {p.id}: {p.nom_affiche} '
                  f'({nb_pos} positions{fe_info}, '
                  f'{nb_tx} transactions, {nb_valo} valorisations)')

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

        confirm = input(
            f'⚠️  Supprimer toutes les données de {len(target_ids)} '
            f'portefeuille(s) ?\n'
            f'   (Les Fonds € seront PRÉSERVÉS mais leur quantité remise à 0)\n'
            f'   Tape "OUI" pour confirmer : '
        )
        if confirm != 'OUI':
            print('Annulé.')
            return

        for pid in target_ids:
            p = session.get(Portefeuille, pid)
            if not p:
                continue

            nb_pos_total = len(p.positions)
            nb_tx = len(p.transactions)
            nb_valo = len(p.valorisations)

            # 🛡️ Séparer les positions à supprimer vs à préserver
            positions_to_delete = [
                pos for pos in p.positions
                if pos.categorie not in RESERVES_CATEGORIES
            ]
            positions_to_preserve = [
                pos for pos in p.positions
                if pos.categorie in RESERVES_CATEGORIES
            ]

            # Supprimer les positions classiques
            for pos in positions_to_delete:
                session.delete(pos)

            # 🆕 Réinitialiser les Fonds € préservés
            for pos in positions_to_preserve:
                pos.quantite = 0.0
                pos.prix_moyen = 1.0
                pos.cours_actuel = 1.0

            # Supprimer toutes les transactions et valorisations
            for tx in list(p.transactions):
                session.delete(tx)
            for v in list(p.valorisations):
                session.delete(v)

            nb_supprimees = len(positions_to_delete)
            nb_preservees = len(positions_to_preserve)
            preserve_info = (
                f', 🛡️ {nb_preservees} Fonds € préservé(s) (réinitialisé(s) à 0)'
                if nb_preservees else ''
            )
            print(f'   ✅ Portefeuille {pid} : {nb_supprimees} position(s) supprimée(s)'
                  f'{preserve_info}, {nb_tx} transactions, {nb_valo} valorisations supprimées')

        # Optionnel : nettoyer aussi CoursHistorique
        clean_cours = input('\nSupprimer aussi tout l\'historique des cours ? (o/N) : ')
        if clean_cours.lower() == 'o':
            session.query(CoursHistorique).delete()
            print('   ✅ Historique des cours vidé')

        session.commit()

    print('\n✅ Reset terminé !')


if __name__ == '__main__':
    reset_portfolio_data()