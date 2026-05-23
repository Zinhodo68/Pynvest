"""Service de mise à jour automatique des cours."""
from datetime import date, timedelta
from sqlalchemy import select, or_

from database.db import get_session
from database.models import Position, CoursHistorique, Valorisation, Portefeuille, Transaction
from services.market_data import get_current_price_with_currency, get_currency_rate
from services._state import get_last_update_date, set_last_update_date


def update_all_quotes(force: bool = False) -> dict:
    """Met à jour les cours de toutes les positions avec auto_update=True.
    Si auto_update=False ou si l'API échoue, on utilise le prix du dernier achat.
    Si force=False : ne fait rien si déjà mis à jour aujourd'hui.
    Retourne un dict avec stats : {'updated': N, 'errors': N, 'skipped': N}
    """
    last_update = get_last_update_date()
    today = date.today()

    if not force and last_update == today:
        print(f'⏭️  Cours déjà à jour ({last_update})')
        return {'updated': 0, 'errors': 0, 'skipped': 0, 'status': 'up_to_date'}

    print(f'🔄 Mise à jour des cours (dernière MAJ : {last_update or "jamais"})')

    stats = {'updated': 0, 'errors': 0, 'skipped': 0, 'status': 'ok'}

    with get_session() as session:
        # 1. Récupérer TOUTES les positions (hors Cash et Fonds Euro)
        positions = session.execute(
            select(Position).where(
                Position.nom != 'Cash',
                Position.categorie != 'Fonds Euro',
                Position.categorie != 'Fonds €'
            )
        ).scalars().all()

        # 2. Séparer par type de mise à jour et dédupliquer
        unique_tickers_auto = {}
        positions_manuelles = []

        for pos in positions:
            if pos.auto_update:
                key = pos.ticker or pos.code
                if key and key not in unique_tickers_auto:
                    unique_tickers_auto[key] = {
                        'ticker': pos.ticker,
                        'isin': pos.code,
                        'devise_position': pos.devise or 'EUR',
                    }
            else:
                positions_manuelles.append(pos)

        print(f'   {len(unique_tickers_auto)} titres auto uniques à mettre à jour via API')
        print(f'   {len(positions_manuelles)} titres manuels (recherche du dernier prix d\'achat)')

        # 3. Récupérer les cours via API
        new_quotes = {}  # {key: cours_eur}
        for key, info in unique_tickers_auto.items():
            try:
                source = 'yahoo' if info['ticker'] else 'boursorama'
                quote_info = get_current_price_with_currency(
                    info['ticker'] or info['isin'], source
                )

                if quote_info['price'] is None:
                    print(f'   ⚠️  Pas de cours API pour {key} -> Fallback sur historique')
                    continue

                cours_eur = quote_info['price']
                if quote_info['currency'] != 'EUR':
                    rate = get_currency_rate(quote_info['currency'], 'EUR')
                    if rate is None:
                        print(f'   ⚠️  Conversion impossible pour {key}')
                        continue
                    cours_eur = quote_info['price'] * rate

                new_quotes[key] = cours_eur

                hist = CoursHistorique(
                    ticker=info['ticker'],
                    isin=info['isin'],
                    date_cours=today,
                    cours=cours_eur,
                    devise='EUR',
                    source=source,
                )
                session.add(hist)
                stats['updated'] += 1

            except Exception as e:
                print(f'   ❌ Erreur API pour {key}: {e}')

        # 4. Mettre à jour les cours des positions (Auto réussies)
        for pos in positions:
            if pos.auto_update:
                key = pos.ticker or pos.code
                if key in new_quotes:
                    pos.cours_actuel = new_quotes[key]

        # 4bis. FALLBACK : Recherche du dernier prix d'achat
        for pos in positions:
            key = pos.ticker or pos.code
            is_failed_auto = pos.auto_update and key not in new_quotes

            if not pos.auto_update or is_failed_auto:

                # Création dynamique des conditions pour éviter le bug des valeurs "NULL"
                conditions = [Transaction.nom_titre == pos.nom]
                if pos.ticker:
                    conditions.append(Transaction.ticker == pos.ticker)
                if pos.code:
                    conditions.append(Transaction.code == pos.code)

                # Recherche de la dernière transaction d'achat pour CE titre exact
                last_buy = session.execute(
                    select(Transaction).where(
                        Transaction.portefeuille_id == pos.portefeuille_id,
                        Transaction.type_operation == 'achat',
                        or_(*conditions)
                    ).order_by(Transaction.date_operation.desc(), Transaction.id.desc())
                ).scalars().first()

                if last_buy and last_buy.prix_unitaire:
                    pos.cours_actuel = last_buy.prix_unitaire
                    if not pos.auto_update:
                        stats['updated'] += 1

        # 5. Snapshot quotidien des valorisations de chaque portefeuille
        portefeuilles = session.execute(select(Portefeuille)).scalars().all()
        for p in portefeuilles:
            valo = sum(pos.valorisation for pos in p.positions)
            if valo > 0:
                existing = session.execute(
                    select(Valorisation).where(
                        Valorisation.portefeuille_id == p.id,
                        Valorisation.date_valeur == today,
                    )
                ).scalar_one_or_none()

                if existing:
                    existing.montant = valo
                else:
                    session.add(Valorisation(
                        portefeuille_id=p.id,
                        date_valeur=today,
                        montant=valo,
                    ))

        session.commit()

        # Backfill des valorisations historiques
        from services.backfill import backfill_portefeuille
        with get_session() as session:
            portefeuille_ids = [p_id for (p_id,) in session.execute(select(Portefeuille.id)).all()]

        for p_id in portefeuille_ids:
            try:
                backfill_portefeuille(p_id)
            except Exception as e:
                print(f'   ⚠️ Backfill échoué pour portefeuille {p_id}: {e}')

        set_last_update_date(today)
        print(f'✅ Mise à jour terminée : {stats}')
        return stats


def get_quotes_history(ticker: str = None, isin: str = None, since: date = None) -> list[dict]:
    """Retourne l'historique des cours d'un titre."""
    with get_session() as session:
        stmt = select(CoursHistorique).order_by(CoursHistorique.date_cours)
        if ticker:
            stmt = stmt.where(CoursHistorique.ticker == ticker)
        if isin:
            stmt = stmt.where(CoursHistorique.isin == isin)
        if since:
            stmt = stmt.where(CoursHistorique.date_cours >= since)

        results = session.execute(stmt).scalars().all()
        return [r.to_dict() for r in results]