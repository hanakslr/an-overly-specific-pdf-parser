from typing import Optional

from pydantic import BaseModel, computed_field


class Block(BaseModel):
    id: str  # UUID

    @computed_field
    @property
    def text(self) -> Optional[str]:
        """Get the text field"""
        raise Exception("Child must implement text property")
