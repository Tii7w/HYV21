from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..network.rate_limiter import TokenBucket
from ..schemas import LoginRequest
from ..security import SESSION_COOKIE, create_session_token, current_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
LOGIN_ATTEMPTS: dict = {}


def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    client = request.client.host if request.client else "unknown"
    # Yalnızca hatalı denemeler jeton harcar: dakikada 5 yanlış şifreden sonra giriş beklemeye alınır.
    bucket = LOGIN_ATTEMPTS.setdefault(client, TokenBucket(5, 60.0))
    if bucket.wait_time() > 0:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Çok fazla hatalı deneme. Bir dakika sonra tekrar deneyin.")

    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        bucket.try_consume()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı adı veya şifre hatalı.")

    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE, create_session_token(user), max_age=settings.session_hours * 3600,
        httponly=True, samesite="strict", secure=settings.cookie_secure, path="/",
    )
    return _user_dict(user)


@router.post("/logout")
def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    # Sürüm artırılarak çalınmış çerezler de geçersiz kılınır.
    db_user = db.get(User, user.id)
    db_user.session_version += 1
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return _user_dict(user)
