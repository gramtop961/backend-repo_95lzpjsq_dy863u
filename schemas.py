"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

# Domain schemas for the Competency Matrix app

class CompetencyMatrixEntry(BaseModel):
    """
    Represents mapping of a job title to its competencies.
    Example document shape (flexible to your JSON):
    {
      "job_title": "Senior Service Delivery Engineer",
      "competencies": [
          {"key": "coaching", "label": "Coaching"},
          {"key": "communication", "label": "Communication"}
      ]
    }
    """
    job_title: str = Field(..., description="Exact job title name")
    competencies: List[Dict[str, Any]] = Field(default_factory=list, description="List of competencies for this title")

class CompetencyStandard(BaseModel):
    """
    Defines standards/levels for a job level (e.g., Junior/Mid/Senior/Lead) per competency.
    Example:
    {
      "job_title": "Service Delivery Engineer",
      "level": "Senior",
      "standards": {
        "coaching": "average",
        "communication": "advanced"
      }
    }
    """
    job_title: str = Field(..., description="Base job title without level, or full title if your JSON uses that")
    level: str = Field(..., description="Level name (e.g., Junior, Senior, Staff)")
    standards: Dict[str, Any] = Field(default_factory=dict, description="Map competency key -> level/expectation value")

class CompetencyDefinition(BaseModel):
    """
    Definition and rubric for each competency term/value, including phrases like "coaching average".
    Example:
    {
      "key": "coaching",
      "label": "Coaching",
      "values": {
         "basic": "Can mentor on simple tasks",
         "average": "Provides regular guidance to peers",
         "advanced": "Develops coaching programs"
      },
      "description": "Ability to help others grow"
    }
    """
    key: str = Field(..., description="Unique competency identifier")
    label: Optional[str] = Field(None, description="Human readable competency name")
    description: Optional[str] = Field(None, description="General description of the competency")
    values: Optional[Dict[str, str]] = Field(default_factory=dict, description="Map of standard/level term -> definition text")

# Example schemas kept for reference (not used directly by this app)
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
