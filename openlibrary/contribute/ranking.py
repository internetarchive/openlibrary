"""How much a task is worth, for picking one at random.

Supply already orders the list by readers. Points per field come from the
scope file and mirror the Edition Scorecard weights, so "valuable" means the
same thing here as on the edit form.
"""

from typing import TYPE_CHECKING

from openlibrary.contribute.scope import Scope, load_scope

if TYPE_CHECKING:
    from openlibrary.contribute.tasks import Task


def task_points(task: Task, scope: Scope | None = None) -> int:
    scope = scope or load_scope()
    return scope.fields[task.field].points if task.field in scope.fields else 0


def impact(readers: int | None, task: Task, scope: Scope | None = None) -> int:
    """Readers times the task's points. A book nobody has logged still counts by its task."""
    return max(readers or 0, 1) * task_points(task, scope)
