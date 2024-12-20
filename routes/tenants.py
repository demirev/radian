import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from core.config import logger, tenant_collections
from core.models import Tenant

tenants_router = APIRouter(prefix="/tenants", tags=["tenants"])

@tenants_router.get("/", response_model=List[Tenant])
async def list_tenants():
	# all tenants in the tenant_collections object
	return tenant_collections.all_tenants


@tenants_router.post("/create", response_model=Tenant)
async def create_tenant(
	tenant_id: str,
	name: Optional[str] = None, 
	description: Optional[str] = None
):
	all_tenants = tenant_collections.all_tenants
	if any(t.tenant_id == tenant_id for t in all_tenants):
		raise HTTPException(status_code=400, detail="Tenant ID already exists")
	tenant = Tenant(tenant_id=tenant_id, name=name, description=description)
	tenant_collections.add_new_tenant(tenant.model_dump(exclude_none=True))
	return tenant


@tenants_router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(
	tenant_id: str,
):
	all_tenants = tenant_collections.all_tenants
	tenant = next((t for t in all_tenants if t.tenant_id == tenant_id), None)
	if not tenant:
		raise HTTPException(status_code=404, detail="Tenant not found")
	return tenant


@tenants_router.delete("/{tenant_id}")
async def delete_tenant(
	tenant_id: str
):
	tenant_collections.remove_tenant(tenant_id)
	return {"message": "Tenant deleted successfully"}


@tenants_router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(
	tenant_id: str,
	name: Optional[str] = None, 
	description: Optional[str] = None
):
	all_tenants = tenant_collections.all_tenants
	tenant = next((t for t in all_tenants if t.tenant_id == tenant_id), None)
	if not tenant:
		raise HTTPException(status_code=404, detail="Tenant not found")
	if name:
		tenant.name = name
	if description:
		tenant.description = description
	if name or description:
		tenant_collections.tenants_collection.update_one(
			{"tenant_id": tenant_id},
			{"$set": tenant.model_dump(exclude_none=True)}
		)
	return tenant
