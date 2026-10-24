import secrets
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    # Changer de mot de passe change la clé : les jetons des autres appareils ne valent plus rien
    session_key = Column(String, nullable=False, default=lambda: secrets.token_hex(16))
    # Clé du widget et des Raccourcis iPhone, gardée sous forme d'empreinte (montrée une seule fois)
    widget_key_hash = Column(String, nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)


class Event(Base):
    """Un fait de la journée. kind : wake (lever), nap (sieste), bed (coucher pour la nuit),
    night (réveil nocturne), feed (biberon). Heures locales « AAAA-MM-JJ HH:MM »."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False, index=True)
    start = Column(String, nullable=False, index=True)
    end = Column(String, nullable=True)
    ml = Column(Integer, nullable=True)
    # Ce que l'app prévoyait au moment du geste (siestes et coucher), pour mesurer plus tard
    # l'écart entre prévision et réalité. Jamais affiché ni modifié ensuite.
    planned_start = Column(String, nullable=True)
    planned_end = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Weight(Base):
    """Une pesée (chez le pédiatre, à la maison). Sert seulement au repère de lait, jamais aux siestes."""
    __tablename__ = "weights"
    id = Column(Integer, primary_key=True)
    day = Column(String, nullable=False, index=True)    # AAAA-MM-JJ
    grams = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
