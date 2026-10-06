"""Which books to show first.

Supply says which books are candidates; this module orders them. A row is
a book plus its open tasks. The two orderings:

- ``impact``: readers helped times the most valuable open task. "Most needed".
- ``points``: the supply's own groups first (the reader's shelves, read
  before want-to-read), then the most valuable open task within each.

Points per field come from the scope file and mirror the Edition Scorecard
weights, so "valuable" means the same thing here as on the edit form.
"""

from typing import TYPE_CHECKING, Literal

from openlibrary.first_edits.scope import Scope, load_scope

if TYPE_CHECKING:
    from openlibrary.first_edits.tasks import Task

Ordering = Literal["impact", "points"]


def task_points(task: Task, scope: Scope | None = None) -> int:
    scope = scope or load_scope()
    return scope.fields[task.field].points if task.field in scope.fields else 0


def top_points(tasks: list[Task], scope: Scope | None = None) -> int:
    scope = scope or load_scope()
    return max((task_points(t, scope) for t in tasks), default=0)


def impact(readers: int | None, tasks: list[Task], scope: Scope | None = None) -> int:
    """Readers times best task. A book nobody has logged still ranks by its task, so the list is never empty of order."""
    return max(readers or 0, 1) * top_points(tasks, scope)


def order_rows(rows: list, by: Ordering, scope: Scope | None = None) -> list:
    """``rows`` are ``(candidate, tasks)`` pairs. Stable, so ties keep the supply's order."""
    scope = scope or load_scope()
    if by == "impact":
        return sorted(rows, key=lambda r: -impact(r[0].readers, r[1], scope))
    return sorted(rows, key=lambda r: (r[0].group, -top_points(r[1], scope)))
