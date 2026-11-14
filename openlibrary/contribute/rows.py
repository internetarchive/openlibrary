"""The shape of the book cards <ol-task-book> and <ol-task-rows> render, for /tasks/rows.json and the pages that embed it."""

from __future__ import annotations

from pydantic import BaseModel


class TaskBook(BaseModel):
    key: str
    olid: str
    edit_url: str
    title: str
    authors: str
    cover_url: str | None
    edition_line: str
    isbn13: str | None
    edition_count: int | None
    work_key: str | None
    readers: int | None


class TaskSummary(BaseModel):
    key: str
    field: str
    label: str
    action_label: str
    url: str
    # Only the dashboard's tasks are weighted, for "Surprise me".
    weight: float | None = None


class TaskRow(BaseModel):
    book: TaskBook
    tasks: list[TaskSummary]


class TaskRowsResponse(BaseModel):
    rows: list[TaskRow]


def dump_rows(rows: list[dict]) -> list[dict]:
    """``rows`` through the same models as /tasks/rows.json, so the embedded and fetched JSON can't drift apart."""
    return TaskRowsResponse.model_validate({"rows": rows}).model_dump()["rows"]


def dump_book(book: dict) -> dict:
    return TaskBook.model_validate(book).model_dump()


def dump_tasks(tasks: list[dict]) -> list[dict]:
    return [TaskSummary.model_validate(t).model_dump() for t in tasks]
