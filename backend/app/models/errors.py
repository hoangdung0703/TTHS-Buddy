from pydantic import BaseModel


class ErrorItem(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorItem
