from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import MAX_ID

router = APIRouter(prefix="/centres", tags=["centres"])


@router.post(
    "/",
    response_model=schemas.CentreOut,
    status_code=201,
    summary="Create Diagnostic Centre",
    description="Creates a diagnostic centre that can offer diagnostic tests and accept bookings."
)
def create_centre(
    payload: schemas.CentreCreate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    # Any authenticated user can register a centre for this assignment's
    # scope. In production this would be gated behind an admin/staff role.
    centre = models.DiagnosticCentre(name=payload.name, location=payload.location)
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre


@router.get("/", response_model=List[schemas.CentreOut])
def list_centres(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # Page over centre ids first (a LIMIT on a joined query would cut tests
    # off mid-centre), then load those centres with their tests.
    centre_ids = [
        row[0]
        for row in db.query(models.DiagnosticCentre.id)
        .order_by(models.DiagnosticCentre.id)
        .offset(skip)
        .limit(limit)
        .all()
    ]
    if not centre_ids:
        return []
    return (
        db.query(models.DiagnosticCentre)
        .options(joinedload(models.DiagnosticCentre.tests))
        .filter(models.DiagnosticCentre.id.in_(centre_ids))
        .order_by(models.DiagnosticCentre.id)
        .all()
    )


@router.get("/{centre_id}", response_model=schemas.CentreOut)
def get_centre(centre_id: Annotated[int, Path(ge=1, le=MAX_ID)], db: Session = Depends(get_db)):
    centre = (
        db.query(models.DiagnosticCentre)
        .options(joinedload(models.DiagnosticCentre.tests))
        .filter(models.DiagnosticCentre.id == centre_id)
        .first()
    )
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")
    return centre


@router.post(
    "/{centre_id}/tests", response_model=schemas.TestOut, status_code=status.HTTP_201_CREATED
)
def add_test(
    centre_id: Annotated[int, Path(ge=1, le=MAX_ID)],
    payload: schemas.TestCreate,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    centre = db.get(models.DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")

    test = models.DiagnosticTest(centre_id=centre_id, name=payload.name, price=payload.price)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@router.get("/{centre_id}/tests", response_model=List[schemas.TestOut])
def list_tests(
    centre_id: Annotated[int, Path(ge=1, le=MAX_ID)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    centre = db.get(models.DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centre not found")
    return (
        db.query(models.DiagnosticTest)
        .filter(models.DiagnosticTest.centre_id == centre_id)
        .order_by(models.DiagnosticTest.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
