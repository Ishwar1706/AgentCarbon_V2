from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models.access_control import User
from app.models.sensor import Sensor
from app.models.workflows import Company

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies(user: User = Depends(require_roles("PLANT_OPERATOR", "AUDITOR")), db: Session = Depends(get_db)):
    query = select(Company).where(Company.verification_status == "VERIFIED").order_by(Company.legal_name)
    if user.role == "PLANT_OPERATOR":
        query = query.where(Company.company_id == user.company_id)
    counts = dict(db.execute(select(Sensor.company_id, func.count()).group_by(Sensor.company_id)).all())
    return [{"company_id": c.company_id, "legal_name": c.legal_name, "city": c.city, "state": c.state,
             "industry": c.industry, "has_dataset": c.has_dataset, "sensor_count": counts.get(c.company_id, 0)}
            for c in db.scalars(query)]
