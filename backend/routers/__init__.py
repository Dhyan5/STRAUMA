"""Router package for the NHAA 14566 assessment API."""

from fastapi import APIRouter

from routers import auth, complainant, law, meta, staff

api_router = APIRouter()
api_router.include_router(auth.router)
# The consent router is mounted separately from the auth router but is part of
# the same surface. It must be included: `POST /api/cases` refuses to open a
# case without a current consent row, so omitting this makes the whole
# complainant flow unreachable.
api_router.include_router(auth.consent_router)
api_router.include_router(complainant.router)
api_router.include_router(staff.router)
api_router.include_router(law.router)
api_router.include_router(meta.router)

__all__ = ["api_router", "auth", "complainant", "staff", "law", "meta"]
