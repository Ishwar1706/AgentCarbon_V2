"""Create a user (use when DEMO_MODE=false).
Usage: python backend/scripts/create_user.py EMAIL "Full Name" ROLE [COMPANY_ID]
ROLE = ADMIN | AUDITOR | CREDIT_BUYER | PLANT_OPERATOR   (the password is prompted)"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.access_control import User  # noqa: E402
from app.models.workflows import AuditorApplication  # noqa: E402

if len(sys.argv) < 4:
    sys.exit(__doc__)
email, name, role = sys.argv[1].lower(), sys.argv[2], sys.argv[3].upper()
company = sys.argv[4] if len(sys.argv) > 4 else None
if role not in {"ADMIN", "AUDITOR", "CREDIT_BUYER", "PLANT_OPERATOR"}:
    sys.exit("ROLE must be ADMIN, AUDITOR, CREDIT_BUYER or PLANT_OPERATOR.")
password = getpass.getpass("Password (min 10 chars): ")
if len(password) < 10:
    sys.exit("Password too short.")
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    if db.scalar(select(User).where(User.email == email)):
        sys.exit("User already exists.")
    user = User(email=email, full_name=name, role=role, company_id=company, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    if role == "AUDITOR":
        db.add(AuditorApplication(application_id=f"AAPP-{user.id:06d}", applicant_user_id=user.id,
                                  organization="Created by administrator", credentials="CLI", status="APPROVED"))
    db.commit()
print("Created", email, role)
