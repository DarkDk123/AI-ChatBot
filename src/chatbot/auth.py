"""Authentication module for ChatBot API."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Optional

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.chatbot.datastore.users import (
    create_user,
    create_users_table,
)
from src.chatbot.datastore.users import (
    get_user as get_db_user,
)
from src.chatbot.datastore.users import (
    get_user_by_email as get_db_user_by_email,
)
from src.chatbot.schemas import Token, User, UserInDB
from src.chatbot.utils import AsyncConnectionPool, get_async_pool

# Configurations
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# OAuth configurations
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth setup
oauth = OAuth()

oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="github",
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    authorize_url="https://github.com/login/oauth/authorize",
    access_token_url="https://github.com/login/oauth/access_token",
    userinfo_endpoint="https://api.github.com/user",
    client_kwargs={
        "scope": "user:email",
    },
)


# Database dependency
async def get_db():
    """Get database pool dependency"""
    return get_async_pool()


router = APIRouter(prefix="/auth", tags=["Authentication"])


# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # Use consistent hashing parameters to ensure same password generates same hash
    return pwd_context.hash(password, scheme="bcrypt", rounds=12)


# def get_user(db: Dict[str, Dict[str, Any]], username: str) -> Optional[UserInDB]:
#     user_data = db.get(username)
#     return UserInDB(**user_data) if user_data else None


# Update the utility functions
async def get_user(pool: AsyncConnectionPool, username: str) -> Optional[UserInDB]:
    """Get user from database"""
    user_data = await get_db_user(pool, username)
    return UserInDB(**user_data) if user_data else None


async def authenticate_user(
    pool: AsyncConnectionPool, username: str, password: str
) -> Optional[User]:
    logging.info("Authenticating user: %s", username)
    user = await get_user(pool, username)
    if not user:
        return None

    # If user has no hashed_password, they are an OAuth user
    if user.hashed_password is None:
        logging.warning("Attempted password login for OAuth user: %s", username)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return User(**user.model_dump())


def create_session_token(
    user_data: User, expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    token_data = {
        "sub": user_data.email or user_data.username,
        "exp": expire.timestamp(),
        "user": user_data.model_dump(),
    }

    logging.info("token_data: %s", token_data)
    return jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)


async def verify_session_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if float(payload["exp"]) < datetime.now(timezone.utc).timestamp():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
            )
        return payload["user"]
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


# Dependency for protected routes using bearer token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    return await verify_session_token(token)


async def create_or_get_user_in_db(
    pool: AsyncConnectionPool, user_info: Dict[str, Any], provider: str = "local"
) -> User:
    username = user_info.get("username") or user_info.get("email")
    email = str(user_info.get("email"))

    if not username:
        logging.error("Invalid user data: missing username or email")
        raise HTTPException(status_code=400, detail="Invalid user data")

    # Check existing user
    existing_user = await get_db_user(pool, username if provider == "local" else email)
    existing_user_email = await get_db_user_by_email(pool, email)
    if existing_user or existing_user_email:
        if provider == "local":
            logging.error(
                "Username/email already exists in database for provider: %s", provider
            )
            raise HTTPException(
                status_code=400, detail="Username already exists in database"
            )

        return User(**(existing_user or existing_user_email or {}))

    # Create new user
    user_data = {
        "username": username,
        "email": email,
        "full_name": user_info.get("name") or user_info.get("full_name", ""),
        "hashed_password": user_info.get("hashed_password")
        if provider == "local"
        else None,
        "oauth_provider": provider if provider != "local" else None,
        "oauth_id": user_info.get("id") if provider != "local" else None,
    }

    try:
        new_user = await create_user(
            pool=pool,
            username=username,
            email=email,
            full_name=user_data["full_name"],
            hashed_password=user_data["hashed_password"],
            oauth_provider=user_data["oauth_provider"],
            oauth_id=user_data["oauth_id"],
            # Default fields: created_at=Timestampz-Now & disabled=False
        )

        logging.info("User created successfully: %s", username)
        return User(**new_user)
    except Exception as e:
        logging.error("Error creating user: %s", str(e))
        raise HTTPException(status_code=400, detail="User creation failed")


# Routes
@router.get("/")
async def homepage(request: Request):
    """Homepage endpoint that displays user info if logged in, or login options if not."""
    user = request.session.get("user")
    if user:
        data = json.dumps(user, indent=2)
        html = f"""
            <div style="font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px;">
                <h1>Welcome!</h1>
                <div style="background: #f5f5f5; padding: 20px; border-radius: 4px;">
                    <pre style="margin: 0;">{data}</pre>
                </div>
                <a href="{request.url_for("logout")}" style="display: inline-block; margin-top: 20px; padding: 10px 20px; 
                    background: #dc3545; color: white; text-decoration: none; border-radius: 4px;">
                    Logout
                </a>
            </div>
        """
        return HTMLResponse(html)

    return HTMLResponse(f"""
        <div style="font-family: sans-serif; max-width: 800px; margin: 40px auto; text-align: center;">
            <h1>Welcome</h1>
            <p>Please choose a login method or sign up</p>
            <div style="margin: 20px;">
                <div style="margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 4px;">
                    <h2>Sign Up</h2>
                    <form action="{request.url_for("signup")}" method="post" style="margin-bottom: 20px;">
                        <input type="text" name="username" placeholder="Username" style="padding: 8px; margin: 5px;">
                        <input type="password" name="password" placeholder="Password" style="padding: 8px; margin: 5px;">
                        <input type="email" name="email" placeholder="Email" style="padding: 8px; margin: 5px;">
                        <input type="text" name="full_name" placeholder="Full Name (optional)" style="padding: 8px; margin: 5px;">
                        <button type="submit" style="padding: 8px 15px; background: #007bff; color: white; border: none; border-radius: 4px;">
                            Sign Up
                        </button>
                    </form>
                </div>
                <div style="margin-bottom: 30px; padding: 20px; background: #f8f9fa; border-radius: 4px;">
                    <h2>Sign In</h2>
                    <form action="{request.url_for("login_for_access_token")}" method="post" style="margin-bottom: 20px;">
                        <input type="text" name="username" placeholder="Username" style="padding: 8px; margin: 5px;">
                        <input type="password" name="password" placeholder="Password" style="padding: 8px; margin: 5px;">
                        <button type="submit" style="padding: 8px 15px; background: #28a745; color: white; border: none; border-radius: 4px;">
                            Login with Username
                        </button>
                    </form>
                    <a href="{request.url_for("google_login")}" style="display: inline-block; margin: 10px; padding: 10px 20px;
                        background: #4285f4; color: white; text-decoration: none; border-radius: 4px;">
                        Login with Google
                    </a>
                    <a href="{request.url_for("github_login")}" style="display: inline-block; margin: 10px; padding: 10px 20px;
                        background: #333; color: white; text-decoration: none; border-radius: 4px;">
                        Login with GitHub
                    </a>
                </div>
            </div>
        </div>
    """)


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    pool: AsyncConnectionPool = Depends(get_db),
):
    user = await authenticate_user(pool, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_session_token(user)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/login/google")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_auth")
    logging.info("REDIRECT URI: %s", redirect_uri)
    return await oauth.google.authorize_redirect(request, redirect_uri)  # type: ignore


@router.get("/google")
async def google_auth(request: Request, pool: AsyncConnectionPool = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)  # type: ignore
        user_info = token.get("userinfo")
        if not user_info:
            raise HTTPException(status_code=400, detail="Invalid user data")
        user_data = await create_or_get_user_in_db(pool, user_info, "google")
        access_token = create_session_token(user_data)
        logging.info("Google Authorized user: %s", user_data.username)
        return {"access_token": access_token, "token_type": "bearer"}
    except OAuthError as error:
        logging.error("OAuth error during Google authentication: %s", str(error))
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/login/github")
async def github_login(request: Request):
    redirect_uri = request.url_for("github_auth")
    logging.info("REDIRECT URI: %s", redirect_uri)
    return await oauth.github.authorize_redirect(request, redirect_uri)  # type: ignore


@router.get("/github")
async def github_auth(
    request: Request,
    pool: AsyncConnectionPool = Depends(get_db),  # Add database dependency
):
    try:
        # Get access token from GitHub
        token = await oauth.github.authorize_access_token(request)  # type: ignore

        if not token:
            raise HTTPException(
                status_code=400, detail="Failed to get GitHub access token"
            )

        # Get user profile info from GitHub
        user_info = await oauth.github.userinfo(token=token)  # type: ignore

        if not user_info:
            raise HTTPException(status_code=400, detail="Invalid user data")

        # Build consistent user info structure
        user_data = {
            "username": user_info.get("login"),  # GitHub username
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "id": user_info.get("id"),
        }

        # Create/get user in database
        user = await create_or_get_user_in_db(
            pool=pool, user_info=user_data, provider="github"
        )

        access_token = create_session_token(user)
        return {"access_token": access_token, "token_type": "bearer", "user": user_data}

    except OAuthError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as e:
        logging.error("GitHub auth error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=500, detail="Authentication service unavailable"
        )


@router.post("/signup", response_model=User)
async def signup(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    email: str = Form(...),
    full_name: Optional[str] = Form(None),
    pool: AsyncConnectionPool = Depends(get_db),
):
    try:
        hashed_password = get_password_hash(form_data.password)
        user_info = {
            "username": form_data.username,
            "email": email,
            "full_name": full_name,
            "hashed_password": hashed_password,
        }

        new_user = await create_or_get_user_in_db(pool, user_info, "local")
        logging.info("Created user on Signup: %s", new_user.username)
        return new_user
    except Exception as e:
        logging.error("Signup error: %s", str(e))
        raise HTTPException(status_code=400, detail="Registration failed")


@router.get("/logout")
async def logout():
    # For token-based auth, the client simply discards the token.
    return {"message": "Logout by discarding the token on client side"}


@router.get("/protected-test")
async def protected_test(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"message": "This is a protected route", "user": current_user}


__all__ = ["SECRET_KEY", "create_users_table", "get_current_user", "router"]
