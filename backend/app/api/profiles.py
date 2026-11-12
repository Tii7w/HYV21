"""Kayıtlı filtre profilleri; her kullanıcı yalnızca kendi profillerini görür."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SearchProfile, User
from ..schemas import ProfileIn
from ..security import current_user

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def profile_dict(profile: SearchProfile) -> dict:
    return {
        "id": profile.id, "name": profile.name, "filters": profile.filters,
        "created_at": profile.created_at.isoformat() + "Z",
        "last_run_at": profile.last_run_at.isoformat() + "Z" if profile.last_run_at else None,
    }


def owned_profile(db: Session, profile_id: int, user: User) -> SearchProfile:
    profile = db.get(SearchProfile, profile_id)
    if profile is None or profile.user_id != user.id:
        raise HTTPException(404, "Profil bulunamadı.")
    return profile


@router.get("")
def list_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)) -> List[dict]:
    return [profile_dict(p) for p in db.scalars(select(SearchProfile).where(SearchProfile.user_id == user.id).order_by(SearchProfile.name))]


@router.post("", status_code=201)
def create_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    profile = SearchProfile(user_id=user.id, name=body.name.strip(), filters=body.filters.model_dump(mode="json"))
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Bu isimde bir profil zaten var.")
    return profile_dict(profile)


@router.put("/{profile_id}")
def update_profile(profile_id: int, body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    profile = owned_profile(db, profile_id, user)
    profile.name, profile.filters = body.name.strip(), body.filters.model_dump(mode="json")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Bu isimde bir profil zaten var.")
    return profile_dict(profile)


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(owned_profile(db, profile_id, user))
    db.commit()
    return {"ok": True}
