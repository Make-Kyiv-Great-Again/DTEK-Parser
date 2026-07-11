from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

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
    
    region_name: str
    street_name: str
    house_name: str
    
    group_assignment: GroupAssignment
    power_status: str
    status_reason: str
    planned_schedule: PlannedOutageInfo
    weekly_schedule: Optional[List[Dict[str, Any]]] = None
    has_power: bool
    group: str
    last_update: str

class AddressItem(BaseModel):
    streetName: str
    houseName: str

class BatchStatusResponseItem(BaseModel):
    streetName: str
    houseName: str
    status: str
    reason: str
