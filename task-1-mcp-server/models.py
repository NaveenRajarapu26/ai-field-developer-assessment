"""Input contracts for the two MCP tools."""

import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    customer_id: str = Field(
        pattern=r"^CUST-[0-9]{5}$",
        description="Exactly CUST- followed by five ASCII digits",
        examples=["CUST-12345"],
    )

    @field_validator("customer_id")
    @classmethod
    def check_full_customer_id(cls, value: str) -> str:
        # Unlike $ in regex, fullmatch also rejects a trailing newline.
        if re.fullmatch(r"CUST-[0-9]{5}", value) is None:
            raise ValueError("customer_id must match CUST-XXXXX")
        return value


class RefundInput(CustomerInput):
    amount: float = Field(
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Positive, finite Python float (integers are rejected)",
        examples=[100.50],
    )
    reason: str = Field(strict=True, min_length=10)

    @field_validator("amount", mode="before")
    @classmethod
    def require_float(cls, value: object) -> object:
        # Explicit assessment choice: JSON 100.0 is accepted; JSON 100 is not.
        # JSON Schema 'number' itself does not express this distinction.
        if type(value) is not float:
            raise ValueError("amount must be a float, e.g. 100.0")
        return value

    @field_validator("reason")
    @classmethod
    def check_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise ValueError("reason must be at least 10 characters after trimming")
        return cleaned
