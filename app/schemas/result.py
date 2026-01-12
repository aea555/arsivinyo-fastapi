from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")

class Result(Generic[T], BaseModel):
    success: bool = False
    code: str = ""
    status_code: int = 200
    message: Optional[str] = None
    data: Optional[T] = None

    @classmethod
    def ok(cls, code: str, status_code: int = 200) -> "Result[T]":
        return cls(success=True, code=code, status_code=status_code)

    @classmethod
    def fail(cls, code: str, status_code: int = 500) -> "Result[T]":
        return cls(success=False, code=code, status_code=status_code)

    def with_data(self, data: T) -> "Result[T]":
        if not self.success:
            raise ValueError("Cannot add data to a failed result")
        self.data = data
        return self

    def with_message(self, message: str) -> "Result[T]":
        self.message = message
        return self
