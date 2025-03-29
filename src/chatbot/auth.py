"""Authentication module for ChatBot API."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.chatbot.schemas import Token, User, UserInDB

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
    client_kwargs={
        "scope": "openid email profile",
        "redirect_url": "http://localhost:8001/auth/google",
    },
)

oauth.register(
    name="github",
    client_id=GITHUB_CLIENT_ID,
    client_secret=GITHUB_CLIENT_SECRET,
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "user:email"},
)

# Fake Users DB (to be replaced with a real database)
fake_users_db: Dict[str, Dict[str, Any]] = {
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": pwd_context.hash("secret123"),
        "disabled": False,
        "created_at": datetime.now(timezone.utc),
    }
}

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Utility functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_user(db: Dict[str, Dict[str, Any]], username: str) -> Optional[UserInDB]:
    user_data = db.get(username)
    return UserInDB(**user_data) if user_data else None


def authenticate_user(
    db: Dict[str, Dict[str, Any]], username: str, password: str
) -> Optional[UserInDB]:
    user = get_user(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


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

    logging.error("token_data: %s", token_data)
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


# Create or get user helper
async def create_or_get_user_in_db(
    user_info: Dict[str, Any], provider: str = "local"
) -> User:
    username = user_info.get("username") or user_info.get("email")
    if not username:
        raise HTTPException(status_code=400, detail="Invalid user data")
    if username in fake_users_db:
        return User(**fake_users_db[username])
    user_data = {
        "username": username,
        "full_name": user_info.get("name") or user_info.get("full_name", ""),
        "email": user_info.get("email"),
        "hashed_password": get_password_hash(user_info.get("password", SECRET_KEY))
        if provider == "local"
        else None,
        "disabled": False,
        "created_at": datetime.now(timezone.utc),
    }
    # Save in db
    fake_users_db[username] = user_data

    # Return User (excluding password & timestamp)
    return User(**user_data)


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
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    user_data = user
    access_token = create_session_token(user_data)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/login/google")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_auth")
    return await oauth.google.authorize_redirect(request, redirect_uri)  # type: ignore


@router.get("/google")
async def google_auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)  # type: ignore
        user_info = token.get("userinfo")
        if user_info:
            user_data = await create_or_get_user_in_db(user_info, "google")
            access_token = create_session_token(user_data)
            return {"access_token": access_token, "token_type": "bearer"}
    except OAuthError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/login/github")
async def github_login(request: Request):
    redirect_uri = request.url_for("github_auth")
    return await oauth.github.authorize_redirect(request, redirect_uri)  # type: ignore


@router.get("/github")
async def github_auth(request: Request):
    try:
        token = await oauth.github.authorize_access_token(request)  # type: ignore
        resp = await oauth.github.get("user", token=token)  # type: ignore
        user_info = resp.json()
        emails_resp = await oauth.github.get("user/emails", token=token)  # type: ignore
        emails = emails_resp.json()
        primary_email = next(
            (email["email"] for email in emails if email.get("primary")), None
        )
        user_info["email"] = primary_email
        if user_info:
            user_data = await create_or_get_user_in_db(user_info, "github")
            access_token = create_session_token(user_data)
            return {"access_token": access_token, "token_type": "bearer"}
    except OAuthError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/signup", response_model=User)
async def signup(
    form_data: OAuth2PasswordRequestForm = Depends(),
    email: str = Form(...),
    full_name: Optional[str] = Form(None),
):
    if form_data.username in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    hashed_password = get_password_hash(form_data.password)
    user_dict = {
        "username": form_data.username,
        "email": email,
        "full_name": full_name,
        "hashed_password": hashed_password,
        "disabled": False,
        "created_at": datetime.now(timezone.utc),
    }

    user_data = await create_or_get_user_in_db(user_dict, "local")
    logging.info("Created user_data: %s", user_data)
    logging.info("All users %s", fake_users_db.keys())
    return {
        "username": user_data.username,
        "email": user_data.email,
        "full_name": user_data.full_name or "",
        "disabled": user_data.disabled,
    }


@router.get("/logout")
async def logout():
    # For token-based auth, the client simply discards the token.
    return {"message": "Logout by discarding the token on client side"}


@router.get("/protected-test")
async def protected_test(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"message": "This is a protected route", "user": current_user}
