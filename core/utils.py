import fitz
import pytz
from typing import List, Union
from sqlalchemy import create_engine, Table, Column, String, DateTime, text
from sqlalchemy.orm import class_mapper, declarative_base
from pgvector.sqlalchemy import Vector
from datetime import datetime
from pgvector.psycopg2 import register_vector
import requests
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

def read_pdf_text(file_path):
  doc = fitz.open(file_path)
  text = ""
  for page_num in range(doc.page_count):
    page = doc.load_page(page_num)
    text += page.get_text()
  return text


def chunk_text_simple(text, chunk_size=1000):
  return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def chunk_text_paragraphs(text, chunk_size=1000):
  paragraphs = text.split("\n")
  chunks = []
  chunk = ""
  for paragraph in paragraphs:
    if len(chunk) + len(paragraph) < chunk_size:
      chunk += paragraph + "\n"
    else:
      chunks.append(chunk)
      chunk = paragraph + "\n"
  chunks.append(chunk)
  return chunks


def extract_fields_from_list(
    list,
    fields,
    strict=True
  ):
  processed_list = []

  for item in list:
    if strict and not fields.issubset(item):
      raise ValueError(f"Missing required fields in item: {item}")
    
    # Retain only the specified fields
    processed_item = {key: item[key] for key in fields if key in item}
    processed_list.append(processed_item)

  return processed_list


def embed_text_spacy(text, spacy_model = None):
  doc = spacy_model(text)
  return doc.vector


async def cleanup_mongo(collections, queries):
  for collection in collections:
    for query in queries:
      collection.delete_many(query)
  return True


def get_vector_table(table_name, engine, create=False):
  #if table_name in Base.metadata.tables:
  #  return class_mapper(Base.metadata.tables[table_name]).class_
  
  class DynamicDocumentVector(Base):
    __tablename__ = table_name  
    __table_args__ = {'extend_existing': True}
    id = Column(String, primary_key=True)
    name = Column(String)
    document_id = Column(String)
    text = Column(String)
    embedding = Column(Vector(300))  # Assuming 300-dimensional vectors
    created_at = Column(DateTime, default=datetime.utcnow)

  # Create the table
  if create:
    Base.metadata.create_all(engine)
  return DynamicDocumentVector


def create_postgres_table(table_name: str, engine, overwrite=False):
  if overwrite:
    with engine.connect() as conn:
      conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
      conn.execute(text(f'DROP INDEX IF EXISTS "{table_name}_embedding_idx"'))
      conn.commit()

  class VectorModel(Base):
    __tablename__ = table_name
    __table_args__ = {'extend_existing': True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    document_id = Column(String)
    text = Column(String)
    embedding = Column(Vector(300))  # Assuming 300-dimensional vectors
    created_at = Column(DateTime, default=datetime.utcnow)

  # Create the table
  VectorModel.__table__.create(bind=engine, checkfirst=True)

  # Create the index using raw SQL with proper quoting
  with engine.connect() as conn:
    conn.execute(text(f"""
      CREATE INDEX IF NOT EXISTS "{table_name}_embedding_idx" 
      ON "{table_name}" USING ivfflat (embedding vector_cosine_ops)
      WITH (lists = 100);
    """))
    conn.commit()

  return VectorModel


async def create_postgres_extensions(get_db):
  db = next(get_db())
  try:
    db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    db.commit()
  finally:
    db.close()


def send_slack_message_sync(webhook_url, message):
  if not webhook_url:
    return False
  payload = {"text": message}
  response = requests.post(webhook_url, json=payload)
  if response.status_code == 200:
    return True
  else:
    return False


async def send_slack_message(webhook_url, message):
  if not webhook_url:
    return False
  payload = {"text": message}
  response = requests.post(webhook_url, json=payload)
  if response.status_code == 200:
    return True
  else:
    return False
  

def drop_postgres_table(table_name, engine):
  with engine.connect() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
    conn.execute(text(f"DROP INDEX IF EXISTS {table_name}_embedding_idx"))


def add_tz(timestamp):
	if timestamp.tzinfo is None:
		# If timestamp is naive, make it timezone-aware (UTC)
		timestamp = pytz.UTC.localize(timestamp)
	return timestamp
