import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from core.config import settings

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    valid_username = secrets.compare_digest(credentials.username, settings.DASHBOARD_USERNAME)
    valid_password = secrets.compare_digest(credentials.password, settings.DASHBOARD_PASSWORD)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
