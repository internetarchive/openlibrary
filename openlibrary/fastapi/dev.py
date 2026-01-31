import os

import debugpy  # noqa: T100
from fastapi import APIRouter

router = APIRouter()


@router.get("/admin/attach_debugger")
async def attach_debugger():
    """
    Attach the debugger to the running container.
    """
    if os.environ.get('LOCAL_DEV') != 'true':
        return {"status": "Debugger attachment is only allowed in LOCAL_DEV mode."}

    debugpy.listen(('0.0.0.0', 3000))  # noqa: T100
    debugpy.wait_for_client()  # noqa: T100
    return {"status": "Debugger attached."}
