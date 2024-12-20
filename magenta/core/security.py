import os
import jwt
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel
from jwt.exceptions import InvalidTokenError
from pymongo import MongoClient
from core.config import SECRET_KEY, logger, MONGO_HOST, MONGO_PORT, MONGO_DB

# define env vars
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# security-related classes
class Token(BaseModel):
  access_token: str
  token_type: str


class TokenData(BaseModel):
  username: str | None = None


class User(BaseModel):
  username: str
  type: str | None = None
  disabled: bool | None = None


class UserInDB(User):
  hashed_password: str


# password context and oauth2 scheme
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# connect to users db
mongo_client = MongoClient(MONGO_HOST, MONGO_PORT)
db = mongo_client[MONGO_DB]
users_collection = db.users

# helper functions
def verify_password(plain_password, hashed_password):
  return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
  return pwd_context.hash(password)


def get_user(db, username: str):
  user_dict = db.find_one({"username": username})
  if not user_dict:
    return None
  return UserInDB(**user_dict)
  

def authenticate_user(users_collection, username: str, password: str):
  user = get_user(users_collection, username)
  if not user:
    return False
  if not verify_password(password, user.hashed_password):
    return False
  return user


# access token functions
def create_access_token(data: dict, expires_delta: int = None):
  to_encode = data.copy()
  if expires_delta:
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
  else:
    expire = datetime.utcnow() + timedelta(minutes=15)
  to_encode.update({"exp": expire})
  encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
  return encoded_jwt


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
  credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"}
  )
  try:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username: str = payload.get("sub")
    if username is None:
      raise credentials_exception
    token_data = TokenData(username=username)
  except InvalidTokenError:
    raise credentials_exception
  user = get_user(users_collection, username=token_data.username)
  if user is None:
    raise credentials_exception
  return user


async def get_current_active_user(
  current_user: Annotated[User, Depends(get_current_user)],
):
  if current_user.disabled:
    raise HTTPException(status_code=400, detail="Inactive user")
  return current_user


# function for initial user creation
async def create_initial_users(collection, dir):
   # check if dir exists, if not log message and return false
  if not os.path.exists(dir):
    logger.info(f"Directory {dir} does not exist, cannot create initial users")
    return 0
  
  users_created = 0
  for file in os.listdir(dir):
    if file.endswith(".json"):
      with open(os.path.join(dir, file), 'r') as f:
        user = json.load(f)
        user['hashed_password'] = get_password_hash(user['password'])
        del user['password']
        # validate user and insert into db
        userObj = UserInDB(**user)
        if not get_user(collection, userObj.username):
          collection.insert_one(user)
          logger.info(f"Created user {userObj.username}")
          users_created += 1
        else:
          logger.info(f"User {userObj.username} already exists")

  logger.info(f"Created {users_created} users")
  return users_created
