import os
import json
import uuid
from sqlalchemy.orm import Session
from core import logger
from core.models import Prompt
from core.config import spacy_model, get_db
from core.utils import create_postgres_table, get_vector_table, drop_postgres_table
from .document_service import process_document


async def load_prompts_from_files(collections, dir = "data/prompts", drop_collection=False, drop_if_exists=True):
  for collection in collections:
    if drop_collection:
      collection.drop()
    logger.info(f"Dropped prompts collection for tenant.")
  
    for file in os.listdir(dir):
      if file.endswith(".json"):
        with open(os.path.join(dir, file), 'r') as f:
          data = json.load(f)
          
          # data can be one or multiple prompts
          if isinstance(data, list):
            for prompt in data:
              # check if prompt matches Prompt class's attributes
              try:
                Prompt(**prompt)
              except Exception as e:
                logger.error(f"Error loading prompt from file {file}: {e}")
                continue
              
              if drop_if_exists:
                collection.delete_many({"prompt_id": prompt["prompt_id"]})
              
              collection.insert_one(prompt)
              logger.info(f"Loaded prompt {prompt['name']} from file {file}")
          else:
            # check if data matches Prompt class's attributes
            try:
              Prompt(**data)
            except Exception as e:
              logger.error(f"Error loading prompt from file {file}: {e}")
              continue

            if drop_if_exists:
              collection.delete_many({"prompt_id": data["prompt_id"]})

            collection.insert_one(data)
            logger.info(f"Loaded prompt {data['name']} from file {file}")
  return True


async def load_documents_from_files(
	documents_collections,
	dir="data/documents/instructions",
  model=spacy_model,
	drop_collection=False,
	drop_if_exists=True,
	db: Session = next(get_db())
):
	i = 0
	for tenant_id, documents_collection in documents_collections.items():
		i += 1
		logger.info(f"Processing documents collection {i} of {len(documents_collections)}")
		VectorModel = create_postgres_table(tenant_id, db.bind) # ensure table exists
		if drop_collection:
			documents_collection.drop()
			logger.info(f"Dropped documents collection {documents_collection.name}.")
			# Drop the corresponding PostgreSQL table
			drop_postgres_table(tenant_id, db.bind)
			logger.info(f"Dropped PostgreSQL table {tenant_id}.")
	
		all_insert_instructions = []

		for file in os.listdir(dir):
			if file.endswith(".json"):
				with open(os.path.join(dir, file), 'r') as f:
					data = json.load(f)
					if not isinstance(data, list):
						data = [data]
					for insert_instruction in data:
						if "document_id" not in insert_instruction:
							insert_instruction["document_id"] = uuid.uuid4().hex

						if "chunk_size" not in insert_instruction:
							insert_instruction["chunk_size"] = 1000
					
						required_keys = ["document_id", "file_location", "content_type", "name", "type", "metadata", "chunk_size"]
						if not all(key in insert_instruction for key in required_keys):
							logger.error(f"Error loading document from file {file}: missing keys.")
							continue

						all_insert_instructions.append(insert_instruction)

		for insert_instruction in all_insert_instructions:
			document_id = insert_instruction["document_id"]
			file_location = insert_instruction["file_location"]
			content_type = insert_instruction["content_type"]
			name = insert_instruction["name"]
			type = insert_instruction["type"]
			metadata = insert_instruction["metadata"]
			chunk_size = insert_instruction["chunk_size"]
			table_name = tenant_id # using tenant_id as table_name for now, later we might have separate schemas for different tenants

			if drop_if_exists:
				documents_collection.delete_many({"document_id": document_id})
				documents_collection.delete_many({"name": name})
				# Delete from PostgreSQL
				VectorModel = get_vector_table(table_name, db.bind)
				db.query(VectorModel).filter(
					(VectorModel.document_id == document_id) | (VectorModel.name == name)
				).delete(synchronize_session=False)
				db.commit()

			documents_collection.insert_one(
        {
          "document_id": document_id,
          "name": name,
          "type": type,
          "metadata": metadata,
          "status": "pending"
        } 
			)

			await process_document(
				document_id=document_id,
				file_location=file_location,
				content_type=content_type,
				name=name,
				type=type,
				metadata=metadata,
				spacy_model=model,
				documents_collection=documents_collection,
				db=db,
				table_name=table_name,
				chunk_size=chunk_size,
				cleanup_file=False # don't delete this file as it's going to be used for other tenants
			)  # TODO: do this concurrently

			logger.info(f"Imported document {name} from file {file}")    
	
	return True