"""
Authentication Routes.
Endpoints for user authentication and authorization.
"""

import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.models import TokenRequest, TokenResponse, ErrorResponse
from api.database import get_session, User
from api.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

# JWT Bearer scheme
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session)
) -> Optional[User]:
    """
    Dependency to get the current authenticated user.

    Usage:
        @app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            ...
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"}
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré"
        )

    # Get user from database
    result = await session.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé ou inactif"
        )

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session)
) -> Optional[User]:
    """
    Dependency to optionally get the current user.
    Returns None if not authenticated (doesn't raise exception).
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, session)
    except HTTPException:
        return None


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Get access token",
    responses={401: {"model": ErrorResponse}}
)
async def login(
    request: TokenRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Authenticate user and return access token.

    **Token Usage:**
    Include the token in the Authorization header:
    ```
    Authorization: Bearer <token>
    ```
    """
    # Find user
    result = await session.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ce compte est désactivé !"
        )

    # Update last login
    user.last_login = datetime.utcnow()
    await session.commit()

    # Create token
    access_token = create_access_token(
        data={"sub": user.username, "is_admin": user.is_admin}
    )

    expires_in = settings.jwt_expiration_hours * 3600

    logger.info(f"User {user.username} logged in")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in
    )


@router.post(
    "/register",
    summary="Register new user",
    responses={400: {"model": ErrorResponse}}
)
async def register(
    username: str,
    password: str,
    email: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Register a new user account.
    """
    # Check if username exists
    result = await session.execute(
        select(User).where(User.username == username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur existe déjà"
        )

    # Check if email exists
    if email:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette adresse mail existe déjà"
            )

    # Create user
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        is_active=True,
        is_admin=False
    )

    session.add(user)
    await session.commit()

    logger.info(f"New user registered: {username}")

    return {"message": "Utilisateur enregistré avec succès", "Nom d'utilisateur": username}


@router.get(
    "/me",
    summary="Get current user info"
)
async def get_me(user: User = Depends(get_current_user)):
    """
    Get information about the currently authenticated user.
    """
    return {
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
        "last_login": user.last_login
    }


@router.post(
    "/change-username",
    summary="Change username"
)
async def change_username(
    new_username: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Change the current user's username.
    """
    if len(new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nom d'utilisateur doit contenir au moins 3 caractères"
        )
    
    # Check if username already exists
    result = await session.execute(
        select(User).where(User.username == new_username)
    )
    existing = result.scalar_one_or_none()
    
    if existing and existing.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà pris"
        )
    
    user.username = new_username
    await session.commit()
    
    logger.info(f"Username changed for user {user.id} to {new_username}")
    
    return {"message": "Nom d'utilisateur modifié avec succès", "username": new_username}


@router.post(
    "/change-password",
    summary="Change password"
)
async def change_password(
    current_password: str,
    new_password: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Change the current user's password.
    """
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )

    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit contenir au moins 8 caractères"
        )

    user.hashed_password = get_password_hash(new_password)
    await session.commit()

    logger.info(f"Password changed for user {user.username}")

    return {"message": "Mot de passe modifié avec succès"}


@router.post(
    "/drone-token",
    summary="Generate drone API token"
)
async def generate_drone_token(
    drone_id: str,
    user: User = Depends(get_current_user)
):
    """
    Generate a long-lived token for drone authentication.
    Only admin users can generate drone tokens.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilèges administrateur requis"
        )

    # Create long-lived token for drone
    token = create_access_token(
        data={
            "sub": drone_id,
            "type": "drone",
            "created_by": user.username
        },
        expires_delta=timedelta(days=365)  # 1 year
    )

    logger.info(f"Drone token generated for {drone_id} by {user.username}")

    return {
        "drone_id": drone_id,
        "token": token,
        "expires_in": 365 * 24 * 3600
    }