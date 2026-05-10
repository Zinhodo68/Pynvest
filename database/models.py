from sqlalchemy import Column, Integer, String, Date, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.orm import relationship
from database.db import Base


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
    taux_interet = Column(Float, nullable=True)  # ex: 3.0 pour 3%
    plafond = Column(Float, nullable=True)  # ex: 22950 pour Livret A

    # Relations futures (transactions, valorisations)
    valorisations = relationship('Valorisation', back_populates='portefeuille',
                                  cascade='all, delete-orphan',
                                  order_by='Valorisation.date_valeur')
    transactions = relationship('Transaction', back_populates='portefeuille',
                                 cascade='all, delete-orphan',
                                 order_by='Transaction.date_operation')

    @property
    def nom_affiche(self):
        if self.proprietaire:
            return f'{self.type} — {self.proprietaire.prenom}'
        return self.type

    @property
    def valorisation_actuelle(self):
        """Valeur actuelle = somme des positions OU dernière valorisation manuelle.
        Priorité aux positions si elles existent, sinon snapshot manuel."""
        # Si on a des positions, on calcule depuis elles
        if self.positions:
            return sum(pos.valorisation for pos in self.positions)
        # Sinon on retombe sur le dernier snapshot manuel
        if self.valorisations:
            return self.valorisations[-1].montant
        return 0.0

    @property
    def total_verse(self):
        """Somme des versements - retraits."""
        total = 0.0
        for t in self.transactions:
            if t.type_operation == 'versement':
                total += t.montant
            elif t.type_operation == 'retrait':
                total -= t.montant
        return total

    @property
    def plus_value(self):
        """Plus-value latente = valorisation - total versé."""
        return self.valorisation_actuelle - self.total_verse

    @property
    def rendement_total_pct(self):
        """Rendement total en %."""
        if self.total_verse > 0:
            return (self.plus_value / self.total_verse) * 100
        return 0.0

    @property
    def rendement_annualise_pct(self):
        """Rendement annualisé (TRI simplifié)."""
        if not self.date_creation or self.total_verse <= 0:
            return 0.0
        from datetime import date as _date
        nb_jours = (_date.today() - self.date_creation).days
        if nb_jours <= 0:
            return 0.0
        nb_annees = nb_jours / 365.25
        if nb_annees < 0.1:
            return 0.0
        ratio = self.valorisation_actuelle / self.total_verse
        if ratio <= 0:
            return 0.0
        return (ratio ** (1 / nb_annees) - 1) * 100

    def to_dict(self):
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
            'nb_transactions': len(self.transactions),
        }


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
    """Versement, retrait, dividende, frais..."""
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portefeuille_id = Column(Integer, ForeignKey('portefeuilles.id'), nullable=False)
    date_operation = Column(Date, nullable=False)
    type_operation = Column(String(50), nullable=False)  # versement, retrait, dividende, frais
    montant = Column(Float, nullable=False)
    libelle = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    portefeuille = relationship('Portefeuille', back_populates='transactions')


class Position(Base):
    """Une ligne dans un portefeuille multi-supports (action, ETF, SCPI, fonds, crypto...)."""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    portefeuille_id = Column(Integer, ForeignKey('portefeuilles.id'), nullable=False)

    nom = Column(String(200), nullable=False)  # ex: "ETF World", "Apple", "SCPI Primovie"
    code = Column(String(50), nullable=True)  # ISIN, ticker, etc.
    categorie = Column(String(50), nullable=True)  # Action, ETF, SCPI, Fonds, Crypto, Obligation

    quantite = Column(Float, nullable=False, default=0)  # nombre de parts
    prix_moyen = Column(Float, nullable=False, default=0)  # PRU (prix de revient unitaire)
    cours_actuel = Column(Float, nullable=True)  # dernier cours connu

    devise = Column(String(10), default='EUR')
    notes = Column(Text, nullable=True)
    date_ouverture = Column(Date, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    portefeuille = relationship('Portefeuille', back_populates='positions')

    @property
    def prix_revient(self):
        """Coût total d'acquisition."""
        return (self.quantite or 0) * (self.prix_moyen or 0)

    @property
    def valorisation(self):
        """Valeur actuelle de la position."""
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
            'categorie': self.categorie,
            'quantite': self.quantite,
            'prix_moyen': self.prix_moyen,
            'cours_actuel': self.cours_actuel,
            'devise': self.devise,
            'notes': self.notes,
            'date_ouverture': self.date_ouverture.isoformat() if self.date_ouverture else None,
            'prix_revient': self.prix_revient,
            'valorisation': self.valorisation,
            'plus_value': self.plus_value,
            'plus_value_pct': self.plus_value_pct,
        }