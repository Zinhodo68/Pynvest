from typing import ClassVar        # ← ajouter cette ligne
from sqlalchemy.orm import relationship
from database.db import Base
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, CheckConstraint, Date, Float, ForeignKey, Text, Boolean, func

class Membre(Base):
    __tablename__ = 'membres'

    id = Column(Integer, primary_key=True, autoincrement=True)
    prenom = Column(String(100), nullable=False)
    nom = Column(String(100), nullable=False)
    initiales = Column(String(5), nullable=False)
    role = Column(String(50), nullable=False)
    date_naissance = Column(Date, nullable=True)
    email = Column(String(150), nullable=True)
    couleur = Column(String(20), default='#3b82f6')
    created_at = Column(DateTime, server_default=func.now())

    portefeuilles = relationship('Portefeuille', back_populates='proprietaire',
                                 cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'prenom': self.prenom,
            'nom': self.nom,
            'initiales': self.initiales,
            'role': self.role,
            'date_naissance': self.date_naissance.isoformat() if self.date_naissance else None,
            'email': self.email,
            'couleur': self.couleur,
        }


class Portefeuille(Base):
    __tablename__ = 'portefeuilles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    etablissement = Column(String(150), nullable=True)
    date_creation = Column(Date, nullable=True)
    logo_path = Column(String(255), nullable=True)
    url_gestion = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    proprietaire_id = Column(Integer, ForeignKey('membres.id'), nullable=True)
    proprietaire = relationship('Membre', back_populates='portefeuilles')

    created_at = Column(DateTime, server_default=func.now())

    positions = relationship('Position', back_populates='portefeuille',
                             cascade='all, delete-orphan',
                             order_by='Position.nom')

    # ✨ Pour les mono-supports (livrets)
    taux_interet = Column(Float, nullable=True)
    plafond = Column(Float, nullable=True)

    valorisations = relationship('Valorisation', back_populates='portefeuille',
                                 cascade='all, delete-orphan',
                                 order_by='Valorisation.date_valeur')
    transactions = relationship('Transaction', back_populates='portefeuille',
                                cascade='all, delete-orphan',
                                order_by='Transaction.date_operation')

    # ──────────────────────────────────────────────────────────────────────
    # Cache non-persisté pour les stats agrégées
    # Rempli par services.portfolio_stats.preload_stats()
    # ──────────────────────────────────────────────────────────────────────
    _stats_cache: ClassVar[dict | None] = None

    def set_stats(self, stats: dict) -> None:
        """Injecte un dict de stats pré-calculées (depuis portfolio_stats)."""
        self._stats_cache = stats

    def clear_stats(self) -> None:
        """Invalide le cache (à appeler après une modification)."""
        self._stats_cache = None

    # ──────────────────────────────────────────────────────────────────────
    # Propriétés calculées — consultent le cache en priorité
    # ──────────────────────────────────────────────────────────────────────

    @property
    def nom_affiche(self):
        if self.proprietaire:
            return f'{self.type} — {self.proprietaire.prenom}'
        return self.type

    @property
    def valorisation_actuelle(self):
        """Valeur actuelle du portefeuille = somme des positions.

        Priorité :
        1. Cache pré-chargé par ``portfolio_stats.preload_stats()``
        2. Fallback lazy-loading (comportement historique)
        """
        # 1️⃣ Cache agrégé (0 lazy-load)
        if self._stats_cache is not None:
            return self._stats_cache['valorisation_actuelle']

        # 2️⃣ Fallback : lazy loading d'origine
        if self.positions:
            return sum(pos.valorisation for pos in self.positions)
        if self.valorisations:
            return self.valorisations[-1].montant
        return 0.0

    @property
    def total_verse(self):
        """Capital investi = uniquement les flux EXTERNES.

        Exclut les arbitrages internes (transactions avec parent_transaction_id).
        """
        # 1️⃣ Cache agrégé
        if self._stats_cache is not None:
            return self._stats_cache['total_verse']

        # 2️⃣ Fallback
        total = 0.0
        for t in self.transactions:
            if t.parent_transaction_id is not None:
                continue
            if t.type_operation == 'versement':
                total += t.montant
            elif t.type_operation == 'retrait':
                total -= t.montant
        return total

    @property
    def plus_value(self):
        if self._stats_cache is not None:
            return self._stats_cache['plus_value']
        return self.valorisation_actuelle - self.total_verse

    @property
    def rendement_total_pct(self):
        if self._stats_cache is not None:
            return self._stats_cache['rendement_total_pct']
        if self.total_verse > 0:
            return (self.plus_value / self.total_verse) * 100
        return 0.0

    @property
    def rendement_annualise_pct(self):
        """Rendement annualisé (CAGR).

        Utilise les valeurs du cache si disponible,
        sinon retombe sur les @property (lazy-load).
        """
        if self._stats_cache is not None:
            total_verse = self._stats_cache['total_verse']
            valorisation = self._stats_cache['valorisation_actuelle']
        else:
            total_verse = self.total_verse
            valorisation = self.valorisation_actuelle

        if not self.date_creation or total_verse <= 0:
            return 0.0
        from datetime import date as _date
        nb_jours = (_date.today() - self.date_creation).days
        if nb_jours <= 0:
            return 0.0
        nb_annees = nb_jours / 365.25
        if nb_annees < 0.1:
            return 0.0
        ratio = valorisation / total_verse
        if ratio <= 0:
            return 0.0
        return (ratio ** (1 / nb_annees) - 1) * 100

    # ──────────────────────────────────────────────────────────────────────
    # Sérialisation
    # ──────────────────────────────────────────────────────────────────────

    def to_dict(self):
        """Dict pour l'affichage. Utilise le cache si disponible."""
        # nb_transactions : cache ou fallback len(transactions)
        if self._stats_cache is not None:
            nb_transactions = self._stats_cache['nb_transactions']
        else:
            nb_transactions = len(self.transactions)

        return {
            'id': self.id,
            'type': self.type,
            'nom_affiche': self.nom_affiche,
            'etablissement': self.etablissement,
            'date_creation': self.date_creation.isoformat() if self.date_creation else None,
            'logo_path': self.logo_path,
            'url_gestion': self.url_gestion,
            'notes': self.notes,
            'proprietaire_id': self.proprietaire_id,
            'proprietaire_prenom': self.proprietaire.prenom if self.proprietaire else None,
            'proprietaire_nom': f'{self.proprietaire.prenom} {self.proprietaire.nom}' if self.proprietaire else None,
            'proprietaire_couleur': self.proprietaire.couleur if self.proprietaire else None,
            'proprietaire_initiales': self.proprietaire.initiales if self.proprietaire else None,
            'valorisation_actuelle': self.valorisation_actuelle,
            'total_verse': self.total_verse,
            'plus_value': self.plus_value,
            'rendement_total_pct': self.rendement_total_pct,
            'rendement_annualise_pct': self.rendement_annualise_pct,
            'nb_transactions': nb_transactions,
        }


class SupportLabel(Base):
    """Noms personnalisés pour les supports d'investissement."""
    __tablename__ = 'support_labels'

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=True, index=True)
    code = Column(String, nullable=True, index=True)
    custom_name = Column(String, nullable=False)
    original_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint('ticker IS NOT NULL OR code IS NOT NULL',
                        name='ck_support_labels_has_identifier'),
    )


class Valorisation(Base):
    """Snapshot de la valeur du portefeuille à une date donnée."""
    __tablename__ = 'valorisations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portefeuille_id = Column(Integer, ForeignKey('portefeuilles.id'), nullable=False)
    date_valeur = Column(Date, nullable=False)
    montant = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    portefeuille = relationship('Portefeuille', back_populates='valorisations')


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portefeuille_id = Column(Integer, ForeignKey('portefeuilles.id'), nullable=False)
    date_operation = Column(Date, nullable=False)
    type_operation = Column(String(50), nullable=False)
    montant = Column(Float, nullable=False)
    libelle = Column(String(200), nullable=True)

    parent_transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=True)

    # Champs enrichis pour traçabilité historique
    ticker = Column(String(50), nullable=True)
    code = Column(String(50), nullable=True)
    nom_titre = Column(String(200), nullable=True)
    categorie = Column(String(50), nullable=True)
    quantite = Column(Float, nullable=True)
    prix_unitaire = Column(Float, nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    portefeuille = relationship('Portefeuille', back_populates='transactions')
    parent = relationship('Transaction', remote_side=[id], backref='children')


class Position(Base):
    """Une ligne dans un portefeuille multi-supports."""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portefeuille_id = Column(Integer, ForeignKey('portefeuilles.id'), nullable=False)

    nom = Column(String(200), nullable=False)
    code = Column(String(50), nullable=True)
    ticker = Column(String(50), nullable=True)
    categorie = Column(String(50), nullable=True)

    quantite = Column(Float, nullable=False, default=0)
    prix_moyen = Column(Float, nullable=False, default=0)
    cours_actuel = Column(Float, nullable=True)

    devise = Column(String(10), default='EUR')
    notes = Column(Text, nullable=True)
    date_ouverture = Column(Date, nullable=True)

    auto_update = Column(Boolean, default=True)
    last_update = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    portefeuille = relationship('Portefeuille', back_populates='positions')

    @property
    def prix_revient(self):
        return (self.quantite or 0) * (self.prix_moyen or 0)

    @property
    def valorisation(self):
        if self.cours_actuel is not None:
            return (self.quantite or 0) * self.cours_actuel
        return self.prix_revient

    @property
    def plus_value(self):
        return self.valorisation - self.prix_revient

    @property
    def plus_value_pct(self):
        if self.prix_revient > 0:
            return (self.plus_value / self.prix_revient) * 100
        return 0.0

    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'code': self.code,
            'ticker': self.ticker,
            'categorie': self.categorie,
            'quantite': self.quantite,
            'prix_moyen': self.prix_moyen,
            'cours_actuel': self.cours_actuel,
            'devise': self.devise,
            'notes': self.notes,
            'date_ouverture': self.date_ouverture.isoformat() if self.date_ouverture else None,
            'auto_update': self.auto_update,
            'prix_revient': self.prix_revient,
            'valorisation': self.valorisation,
            'plus_value': self.plus_value,
            'plus_value_pct': self.plus_value_pct,
        }


class CoursHistorique(Base):
    """Historique quotidien des cours (1 ligne par titre par jour)."""
    __tablename__ = 'cours_historique'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(50), nullable=True, index=True)
    isin = Column(String(50), nullable=True, index=True)
    date_cours = Column(Date, nullable=False, index=True)
    cours = Column(Float, nullable=False)
    devise = Column(String(10), default='EUR')
    source = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            'ticker': self.ticker,
            'isin': self.isin,
            'date': self.date_cours.isoformat(),
            'cours': self.cours,
            'devise': self.devise,
        }
from sqlalchemy import event

@event.listens_for(Position.prix_moyen, 'set')
def _watch_prix_moyen(target, value, oldvalue, initiator):
    """Log toute modification de prix_moyen pour debug."""
    import traceback
    if oldvalue is not None and value is not None:
        try:
            oldv = float(oldvalue) if oldvalue else 0
            newv = float(value) if value else 0
            # Alerte si baisse de plus de 50%
            if oldv > 1 and newv > 0 and (newv / oldv) < 0.5:
                print(f'⚠️⚠️⚠️ ALERTE PRU DIVISÉ : {target.nom} '
                      f'{oldv:.4f} → {newv:.4f}')
                print('   Stack trace :')
                traceback.print_stack(limit=8)
        except (TypeError, ValueError):
            pass