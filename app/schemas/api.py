from typing import List, Optional, Dict
from pydantic import BaseModel, Field

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

class GroupAssignment(BaseModel):
    group: int
    subgroup: int
    raw_group_key: str
    mapped_group_key: str

class OutageSlotSchema(BaseModel):
    start: int
    end: int
    type: str

class PlannedDayOutages(BaseModel):
    date: str
    status: str
    slots: List[OutageSlotSchema]

class PlannedOutageInfo(BaseModel):
    today: Optional[PlannedDayOutages] = None
    tomorrow: Optional[PlannedDayOutages] = None
    updatedOn: Optional[str] = None

class StatusResponse(BaseModel):
    region_id: int
    street_id: int
    house_id: int
    dso_id: int
    address: str
    group_info: GroupAssignment
    power_status: str = Field(description="ON, OFF, or EMERGENCY")
    status_reason: str
    planned_schedule: Optional[PlannedOutageInfo] = None
    weekly_schedule: Optional[Dict[str, List[OutageSlotSchema]]] = None
    has_power: bool
    group: str
    last_update: Optional[str] = None

class AddressItem(BaseModel):
    streetName: str
    houseName: str

class BatchStatusResponseItem(BaseModel):
    streetName: str
    houseName: str
    status: str
