import os
# import spacy
import json
from loguru import logger
from pymongo import MongoClient
from openai import OpenAI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Tenant


# add logger
logger.add(
	os.getenv("LOG_FILE", "logs/app.log"),
	rotation=os.getenv("LOG_ROTATION", "500 MB"),
	retention=os.getenv("LOG_RETENTION", "10 days"),
	level=os.getenv("LOG_LEVEL", "INFO")
)


# read env vars
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'magenta')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
MONGO_HOST = os.getenv('MONGO_HOST', 'localhost')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'magenta')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
SECRET_KEY = os.getenv('SECRET_KEY')


# load the spacy model
# spacy_model = spacy.load("en_core_web_lg")
spacy_model = None

# establish connection to MongoDB
mongo_client = MongoClient(MONGO_HOST, MONGO_PORT)
system_db = mongo_client[MONGO_DB]
tenants_collection = system_db.tenants


class TenantCollections:
	def __init__(self, mongo_client, tenant_files_dir=None):
		self.mongo_client = mongo_client
		self.tenants_collection = tenants_collection
		self.tenant_files_dir = tenant_files_dir
		self.collections = {
			"tasks": {}, "prompts": {}, 
			"documents": {}, "chats": {},
			"tools": {}
		}
		self.all_tenants = []
		self.get_all_tenants()
		self._register_default_collections()

	def get_all_tenants(self):
		known_tenants = self._load_known_tenants()
		db_tenants = list(self.tenants_collection.find())
		defined_tenants_obj = []
		for tenant in db_tenants:
			tenant = Tenant(**tenant)
			defined_tenants_obj.append(tenant)
		self.all_tenants = defined_tenants_obj + known_tenants
		return self.all_tenants

	def _load_known_tenants(self):
		known_tenants = []
		if self.tenant_files_dir:
			for root, _, files in os.walk(self.tenant_files_dir):
				for file in files:
					if file.endswith('.json'):
						with open(os.path.join(root, file), 'r') as f:
							tenant_data = json.load(f)
							# check if tenant_data is a list
							if isinstance(tenant_data, list):
								for tenant in tenant_data:
									tenant = Tenant(**tenant)
									known_tenants.append(tenant)
							else:
								tenant = Tenant(**tenant_data)
								known_tenants.append(tenant)
		logger.info(f"Loaded {len(known_tenants)} known tenants: {known_tenants}")
		return known_tenants

	def _register_default_collections(self):
		default_db = self.mongo_client["default"]
		for collection_name in self.collections:
			self.collections[collection_name]["default"] = getattr(default_db, collection_name)

		for tenant in self.all_tenants:
			self._register_tenant_collections(tenant.model_dump()['tenant_id'])

	def _register_tenant_collections(self, tenant_id):
		tenant_db = self.mongo_client[tenant_id]
		for collection_name in self.collections:
			self.collections[collection_name][tenant_id] = getattr(tenant_db, collection_name)

	def get_collection(self, tenant_id: str, collection_name: str, search_db=False):
		if collection_name in self.collections and tenant_id in self.collections[collection_name]:
			return self.collections[collection_name][tenant_id]
		elif search_db:
			tenant_db = self.mongo_client[tenant_id]
			return getattr(tenant_db, collection_name)
		else:
			raise ValueError(f"Tenant data not found for tenant_id: {tenant_id}")
	
	def get_collections_list(self, collection_name: str):
		return list(self.collections[collection_name].values())

	def add_new_tenant(self, tenant_data: dict):
		tenant = Tenant(**tenant_data)
		self.tenants_collection.insert_one(tenant.model_dump(exclude_none=True)) # insert into MongoDB
		self.all_tenants.append(tenant) # add to the list of tenants
		self._register_tenant_collections(tenant.tenant_id)  # Register collections for the new tenant in memory
		logger.info(f"Added new tenant: {tenant_data['tenant_id']}")

	def remove_tenant(self, tenant_id: str):
		for collection_name in self.collections:
			self.collections[collection_name][tenant_id].drop()
		self.tenants_collection.delete_one({"tenant_id": tenant_id})
		self.all_tenants = [t for t in self.all_tenants if t.tenant_id != tenant_id]
		logger.info(f"Removed tenant: {tenant_id}")


tenant_collections = TenantCollections(
	mongo_client=mongo_client,
	tenant_files_dir="data/tenants/"
)
logger.info(f"Initialized collections for {len(tenant_collections.collections)} tenants.")

# PostgreSQL connection
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()


logger.info("Connected to PostgreSQL and MongoDB.")


# Connect to OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY is None:
	raise ValueError("Missing OpenAI API key")
openai_client = OpenAI(api_key=OPENAI_API_KEY)