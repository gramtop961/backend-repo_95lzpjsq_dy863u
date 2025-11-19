import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Competency Matrix API is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------------------- Domain Models ----------------------
class IngestPayload(BaseModel):
    matrix: Any = Field(..., description="General matrix JSON mapping job titles to competencies")
    standards: Any = Field(..., description="Standards JSON defining level per competency per level")
    definitions: Any = Field(..., description="Definitions JSON explaining each competency and level term")
    replace: bool = Field(True, description="If true, clears previous data before insert")


# ---------------------- Helpers ----------------------
MATRIX_COL = "competencymatrixentry"
STANDARDS_COL = "competencystandard"
DEFS_COL = "competencydefinition"


def _clear_collections():
    db[MATRIX_COL].delete_many({})
    db[STANDARDS_COL].delete_many({})
    db[DEFS_COL].delete_many({})


def _normalize_title(title: str) -> str:
    return " ".join(title.split()).strip()


# ---------------------- API: Ingest ----------------------
@app.post("/api/ingest")
def ingest(payload: IngestPayload):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    if payload.replace:
        _clear_collections()

    # Expect flexible JSON shapes; try common patterns
    matrix = payload.matrix
    standards = payload.standards
    definitions = payload.definitions

    # Insert matrix
    # Accept either list of entries or dict mapping title -> list of competencies
    if isinstance(matrix, dict):
        for title, comps in matrix.items():
            create_document(MATRIX_COL, {
                "job_title": _normalize_title(title),
                "competencies": comps if isinstance(comps, list) else []
            })
    elif isinstance(matrix, list):
        for entry in matrix:
            title = _normalize_title(entry.get("job_title") or entry.get("title") or "")
            comps = entry.get("competencies") or entry.get("skills") or []
            if title:
                create_document(MATRIX_COL, {"job_title": title, "competencies": comps})

    # Insert standards
    # Accept shapes like { job_title: { level: { competency: value }}}
    if isinstance(standards, dict):
        for title, lvl_obj in standards.items():
            for lvl, mapping in (lvl_obj or {}).items():
                create_document(STANDARDS_COL, {
                    "job_title": _normalize_title(title),
                    "level": str(lvl),
                    "standards": mapping or {}
                })
    elif isinstance(standards, list):
        for item in standards:
            create_document(STANDARDS_COL, {
                "job_title": _normalize_title(item.get("job_title") or item.get("title") or ""),
                "level": str(item.get("level") or ""),
                "standards": item.get("standards") or item.get("mapping") or {}
            })

    # Insert definitions
    # Accept shapes like { competency_key: { description, values: {level: text}} } or list of entries
    if isinstance(definitions, dict):
        for key, value in definitions.items():
            entry = {
                "key": key,
                "label": value.get("label") if isinstance(value, dict) else None,
                "description": value.get("description") if isinstance(value, dict) else None,
                "values": value.get("values") if isinstance(value, dict) else {}
            }
            create_document(DEFS_COL, entry)
    elif isinstance(definitions, list):
        for d in definitions:
            key = d.get("key") or d.get("id")
            if not key:
                continue
            create_document(DEFS_COL, {
                "key": key,
                "label": d.get("label"),
                "description": d.get("description"),
                "values": d.get("values") or d.get("levels") or {}
            })

    return {"status": "ok"}


# ---------------------- API: Browse ----------------------
@app.get("/api/titles")
def list_titles():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    titles = sorted({doc.get("job_title") for doc in db[MATRIX_COL].find({}, {"job_title": 1}) if doc.get("job_title")})

    # Build levels per title from standards
    levels_by_title: Dict[str, List[str]] = {}
    for doc in db[STANDARDS_COL].find({}, {"job_title": 1, "level": 1}):
        t = doc.get("job_title")
        l = str(doc.get("level"))
        if t and l:
            levels_by_title.setdefault(t, [])
            if l not in levels_by_title[t]:
                levels_by_title[t].append(l)

    for t in levels_by_title:
        levels_by_title[t].sort()

    return {"titles": titles, "levels": levels_by_title}


@app.get("/api/competencies")
def get_competencies(title: str, level: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    title = _normalize_title(title)

    matrix_entry = db[MATRIX_COL].find_one({"job_title": title})
    if not matrix_entry:
        raise HTTPException(status_code=404, detail="Title not found")

    # Get standards mapping for requested level (if provided)
    level_mapping: Dict[str, Any] = {}
    if level:
        st_doc = db[STANDARDS_COL].find_one({"job_title": title, "level": str(level)})
        if st_doc:
            level_mapping = st_doc.get("standards") or {}

    # Fetch all definitions into a map
    defs_map: Dict[str, Dict[str, Any]] = {}
    for d in db[DEFS_COL].find({}):
        defs_map[d.get("key")] = {
            "label": d.get("label"),
            "description": d.get("description"),
            "values": d.get("values") or {}
        }

    result_items = []
    for comp in matrix_entry.get("competencies", []):
        # Support either string keys or {key, label}
        if isinstance(comp, str):
            key = comp
            label = comp.replace("_", " ").title()
        else:
            key = comp.get("key") or comp.get("id") or comp.get("name")
            label = comp.get("label") or comp.get("name") or (key.replace("_", " ").title() if key else None)
        if not key:
            continue
        standard_value = level_mapping.get(key)
        defn = defs_map.get(key, {})
        value_definition = None
        if standard_value is not None:
            # Look up term like "average" under values
            values_map = defn.get("values") or {}
            value_definition = values_map.get(str(standard_value).lower())
        result_items.append({
            "key": key,
            "label": label,
            "standard": standard_value,
            "definition": defn.get("description"),
            "standard_definition": value_definition
        })

    return {"title": title, "level": level, "items": result_items}
