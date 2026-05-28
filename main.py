"""
Noema Thoughts Backend
----------------------
Run:  uvicorn backend.main:app --reload --port 8001
Docs: http://localhost:8001/docs
"""

import os, hashlib, time
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── Database setup ────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "thoughts.db")
engine  = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

class Base(DeclarativeBase):
    pass

class Thought(Base):
    __tablename__ = "thoughts"
    id         = Column(Integer, primary_key=True, index=True)
    title      = Column(String(200), nullable=False)
    body       = Column(Text, nullable=False)
    excerpt    = Column(String(400), nullable=True)   # auto-generated if blank
    category   = Column(String(80),  default="philosophy")
    author     = Column(String(120), default="The Architect")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Admin auth ────────────────────────────────────────────────────────────────
# Set NOEMA_ADMIN_KEY env var in production.  Default is shown only locally.
ADMIN_KEY = os.getenv("NOEMA_ADMIN_KEY", "noema-architect-2024")

def require_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Unauthorised")

# ── Schemas ───────────────────────────────────────────────────────────────────
class ThoughtIn(BaseModel):
    title:    str
    body:     str
    excerpt:  Optional[str] = None
    category: Optional[str] = "philosophy"
    author:   Optional[str] = "The Architect"

class ThoughtOut(BaseModel):
    id:         int
    title:      str
    body:       str
    excerpt:    str
    category:   str
    author:     str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

def _make_excerpt(body: str, explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    text = body.strip()
    if len(text) <= 200:
        return text
    cut = text[:200]
    last_space = cut.rfind(" ")
    return (cut[:last_space] if last_space > 120 else cut) + "…"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Noema Thoughts", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Public routes ─────────────────────────────────────────────────────────────
@app.get("/thoughts", response_model=List[ThoughtOut])
def list_thoughts(
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Thought).order_by(Thought.created_at.desc())
    if category and category != "all":
        q = q.filter(Thought.category == category)
    return q.offset(offset).limit(limit).all()

@app.get("/thoughts/{thought_id}", response_model=ThoughtOut)
def get_thought(thought_id: int, db: Session = Depends(get_db)):
    t = db.query(Thought).filter(Thought.id == thought_id).first()
    if not t:
        raise HTTPException(404, "Thought not found")
    return t

@app.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(Thought.category).distinct().all()
    cats = sorted({r[0] for r in rows if r[0]})
    return {"categories": cats}

# ── Admin routes ──────────────────────────────────────────────────────────────
@app.post("/admin/thoughts", response_model=ThoughtOut, status_code=201,
          dependencies=[Depends(require_admin)])
def create_thought(payload: ThoughtIn, db: Session = Depends(get_db)):
    t = Thought(
        title    = payload.title.strip(),
        body     = payload.body.strip(),
        excerpt  = _make_excerpt(payload.body, payload.excerpt),
        category = (payload.category or "philosophy").strip().lower(),
        author   = (payload.author or "The Architect").strip(),
    )
    db.add(t); db.commit(); db.refresh(t)
    return t

@app.put("/admin/thoughts/{thought_id}", response_model=ThoughtOut,
         dependencies=[Depends(require_admin)])
def update_thought(thought_id: int, payload: ThoughtIn, db: Session = Depends(get_db)):
    t = db.query(Thought).filter(Thought.id == thought_id).first()
    if not t:
        raise HTTPException(404, "Thought not found")
    t.title    = payload.title.strip()
    t.body     = payload.body.strip()
    t.excerpt  = _make_excerpt(payload.body, payload.excerpt)
    t.category = (payload.category or t.category).strip().lower()
    t.author   = (payload.author or t.author).strip()
    t.updated_at = datetime.utcnow()
    db.commit(); db.refresh(t)
    return t

@app.delete("/admin/thoughts/{thought_id}", dependencies=[Depends(require_admin)])
def delete_thought(thought_id: int, db: Session = Depends(get_db)):
    t = db.query(Thought).filter(Thought.id == thought_id).first()
    if not t:
        raise HTTPException(404, "Thought not found")
    db.delete(t); db.commit()
    return {"message": f"Thought '{t.title}' deleted"}

@app.get("/admin/thoughts", response_model=List[ThoughtOut],
         dependencies=[Depends(require_admin)])
def admin_list_thoughts(db: Session = Depends(get_db)):
    return db.query(Thought).order_by(Thought.created_at.desc()).all()

@app.get("/health")
def health():
    return {"status": "alive", "platform": "Noema"}
