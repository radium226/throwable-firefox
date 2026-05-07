from pydantic import BaseModel, Field


class Bookmark(BaseModel):
    title: str
    url: str


class BookmarkFolder(BaseModel):
    title: str
    children: list["BookmarkItem"] = Field(default_factory=list)


BookmarkItem = Bookmark | BookmarkFolder

BookmarkFolder.model_rebuild()
