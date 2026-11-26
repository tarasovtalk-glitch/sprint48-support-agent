import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Scenario(BaseModel):
    source: str = Field(min_length=1, max_length=150)
    as_of: date
    price_until: date | None
    license_until: date | None
    customer: str = Field(min_length=1, max_length=80)
    contract_ref: str = Field(min_length=1, max_length=80)
    previous_order: str = Field(min_length=1, max_length=60)
    product: str = Field(min_length=1, max_length=65)
    quantity: int = Field(gt=0, le=10000)
    renewal_unit_kopecks: int = Field(gt=0)
    new_unit_kopecks: int = Field(gt=0)
    requested_days: int = Field(ge=1, le=365)

    @model_validator(mode='after')
    def check_dates(self):
        if (self.price_until and self.price_until < self.as_of) or (self.license_until and self.license_until <= self.as_of):
            raise ValueError('Scenario needs a current quote and a non-expired license.')
        return self

    def offer(self) -> dict:
        renewal = self.quantity * self.renewal_unit_kopecks
        new = self.quantity * self.new_unit_kopecks
        return {
            **self.model_dump(mode='json'),
            'renewal_total_kopecks': renewal,
            'new_total_kopecks': new,
            'difference_kopecks': new - renewal,
        }


def load_scenario(path: Path) -> Scenario:
    with path.open(encoding='utf-8') as source:
        return Scenario.model_validate(json.load(source))
