from typing import List
from pydantic import BaseModel

class DsoInfo(BaseModel):
    id: int
    name: str

class RegionInfo(BaseModel):
    id: int
    value: str
    hasCities: bool
    dsos: List[DsoInfo]

class StreetInfo(BaseModel):
    id: int
    value: str

class HouseInfo(BaseModel):
    id: int
    value: str
