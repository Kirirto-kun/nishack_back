from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.enums import UserRole


class UserCreate(BaseModel):
    """Регистрация: без жёсткого EmailStr — допускаются локальные домены (.test, .local и т.д.)."""

    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or len(v) < 3:
            raise ValueError("Некорректный email")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # str, не EmailStr: иначе ответ /users/me падает на dev-почтах вроде admin@nishack.test
    email: str
    role: UserRole
