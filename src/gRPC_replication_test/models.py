from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Boolean, DateTime, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy_utils import database_exists, drop_database


from datetime import datetime

Base = declarative_base()


class UserModel(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    logged_in = Column(Boolean, default=False)
    session_id = Column(String, unique=True, nullable=True)


class MessageModel(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'))
    receiver_id = Column(Integer, ForeignKey('users.id'))
    content = Column(String, nullable=False)
    is_received = Column(Boolean, default=False)
    time_stamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    sender = relationship("UserModel", foreign_keys=[sender_id])
    receiver = relationship("UserModel", foreign_keys=[receiver_id])


class DeletedMessageModel(Base):
    __tablename__ = 'deleted_messages'

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey('users.id'))
    receiver_id = Column(Integer, ForeignKey('users.id'))
    content = Column(String, nullable=False)
    is_received = Column(Boolean, default=False)
    original_message_id = Column(Integer, nullable=True)

    sender = relationship("UserModel", foreign_keys=[sender_id])
    receiver = relationship("UserModel", foreign_keys=[receiver_id])


def init_db(database_url, drop_tables=False):

    if database_exists(database_url) and drop_tables:
        drop_database(database_url)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine):
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=engine)
