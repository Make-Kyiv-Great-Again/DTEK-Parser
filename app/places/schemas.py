from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class PlaceResponse(BaseModel):
    id: int = Field(..., description="Unique OpenStreetMap ID for the node")
    type: str = Field(..., description="Mapped type of the place (e.g. restaurant, cafe, shop category)")
    lat: float = Field(..., description="Latitude coordinate of the node")
    lng: float = Field(..., description="Longitude coordinate of the node")
    name: str = Field(..., description="Name of the venue or shop")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Parsed additional OSM tags (website, opening_hours, cuisine, etc.)"
    )
