from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user, is_verified_auditor
from app.models.access_control import User
from app.models.sensor import Sensor
from app.models.workflows import Company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Company).order_by(Company.legal_name)
    if user.role == "PLANT_OPERATOR":
        query = query.where(Company.company_id == user.company_id)
    elif user.role == "AUDITOR":
        if not is_verified_auditor(db, user):
            return []
        query = query.where(Company.verification_status == "VERIFIED")
    elif user.role == "REGULATOR_VIEWER":
        query = query.where(Company.verification_status == "VERIFIED")
    counts = dict(db.execute(select(Sensor.company_id, func.count()).group_by(Sensor.company_id)).all())
    return [{"company_id": c.company_id, "legal_name": c.legal_name, "city": c.city, "state": c.state,
             "industry": c.industry, "verification_status": c.verification_status,
             "has_dataset": c.has_dataset, "sensor_count": counts.get(c.company_id, 0)}
            for c in db.scalars(query)]
