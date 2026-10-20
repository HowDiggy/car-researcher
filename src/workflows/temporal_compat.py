import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

try:
    from temporalio import workflow, activity
    from temporalio.common import RetryPolicy
    HAS_TEMPORAL = True
except ImportError:
    HAS_TEMPORAL = False

    class _MockWorkflowLogger:
        def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
            logger.info(msg, *args, **kwargs)

        def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
            logger.warning(msg, *args, **kwargs)

        def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
            logger.error(msg, *args, **kwargs)

    class _MockWorkflow:
        logger = _MockWorkflowLogger()

        @staticmethod
        def defn(cls: Any) -> Any:
            return cls

        @staticmethod
        def run(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        @staticmethod
        def query(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        @staticmethod
        def signal(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        class unsafe:
            @staticmethod
            def imports_passed_through():
                from contextlib import nullcontext
                return nullcontext()

        @staticmethod
        async def execute_activity(activity_fn: Any, *args: Any, **kwargs: Any) -> Any:
            """Fallback execution for local mock testing."""
            fn_args = kwargs.get("args", args)
            if callable(activity_fn):
                import inspect
                if inspect.iscoroutinefunction(activity_fn):
                    return await activity_fn(*fn_args)
                return activity_fn(*fn_args)
            return None

        @staticmethod
        async def execute_child_workflow(workflow_cls: Any, *args: Any, **kwargs: Any) -> Any:
            """Fallback execution for local mock testing."""
            fn_args = kwargs.get("args", args)
            wf_inst = workflow_cls() if isinstance(workflow_cls, type) else workflow_cls
            if hasattr(wf_inst, "run"):
                return await wf_inst.run(*fn_args)
            return None

    class _MockActivity:
        @staticmethod
        def defn(fn: Any = None, *args: Any, **kwargs: Any) -> Any:
            if fn is None:
                return lambda f: f
            return fn

    workflow = _MockWorkflow()
    activity = _MockActivity()

    class RetryPolicy:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs


__all__ = ["workflow", "activity", "RetryPolicy", "HAS_TEMPORAL"]
