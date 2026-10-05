from typing import Literal
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Intake(Strict):
    intake_key: UUID
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=r"^\+91[6-9][0-9]{9}$")
    age: int = Field(ge=18, le=110, strict=True)
    health_screening: Literal["clear", "review", "urgent"]
    consent: StrictBool
    consent_version: Literal["2026-09-30-v1"]
    whatsapp_opt_in: StrictBool = False

    @field_validator("consent")
    @classmethod
    def consent_required(cls, v):
        if not v:
            raise ValueError("Explicit consent required")
        return v


class ReportIntake(Intake):
    hba1c: float | None = Field(default=None, ge=2, le=25, allow_inf_nan=False)
    fasting_sugar: float | None = Field(
        default=None, ge=20, le=1000, allow_inf_nan=False
    )
    post_meal_sugar: float | None = Field(
        default=None, ge=20, le=1000, allow_inf_nan=False
    )
    sugar_unit: Literal["mg/dL"] = "mg/dL"
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def has_values(self):
        if all(
            v is None for v in [self.hba1c, self.fasting_sugar, self.post_meal_sugar]
        ):
            raise ValueError("Enter a supported value")
        return self


class DietIntake(Intake):
    plan: Literal["routine14", "support30"]
    goal: Literal[
        "Healthier everyday eating",
        "Weight management",
        "Healthy weight gain",
        "Protein & fitness support",
    ]
    measurements: str = Field(default="", max_length=500)
    food_preference: str = Field(min_length=1, max_length=500)
    allergies: str = Field(min_length=1, max_length=500)
    daily_routine: str = Field(min_length=1, max_length=1000)


class Login(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Review(Strict):
    disposition: Literal["eligible", "referred"]
    note: str = Field(min_length=20, max_length=3000)


class Draft(Strict):
    text: str = Field(min_length=40, max_length=12000)


class Note(Strict):
    note: str = Field(min_length=20, max_length=1000)


class Assignment(Strict):
    user_id: UUID


class Approval(Strict):
    version: int = Field(ge=1)
    confirm_reviewed: StrictBool

    @field_validator("confirm_reviewed")
    @classmethod
    def confirm(cls, v):
        if not v:
            raise ValueError("Review confirmation required")
        return v


class CheckinInput(Strict):
    day: Literal[3, 7, 14, 21, 30]
    adherence: Literal["going_well", "some_difficulty", "need_help"]
    note: str = Field(default="", max_length=1500)


class OptIn(Strict):
    whatsapp_opt_in: StrictBool
