import inspect
from typing import Any, Type, cast

from typing_extensions import Self  # type: ignore

from dunetuf.copy.dune.copy_dune import CopyDune


class CopyHomePro(CopyDune):
    """
    Concrete implementation of CopyDune for HomePro-based architecture.

    Currently, no additional logic is implemented.
    """

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        """
        Create a new instance of CopyDune or its subclass.
        Returns:
            An instance of CopyDune or its subclass.
        """
        # Verify that instantiation is coming from 'CopyDune'
        caller_frame = inspect.stack()[1]
        caller_module = inspect.getmodule(caller_frame[0])
        if caller_module is None or not (
            caller_module.__name__.startswith("dunetuf.copy.copy_dune.copydune")
        ):
            raise RuntimeError(
                "CopyHomePro (and its subclasses) can only be instantiated via CopyDune."
            )
        if cls is CopyHomePro:
            if cls._family_name == "enterprise":
                from dunetuf.copy.dune.homepro.copy_beam import CopyBeam

                cls = cast(Type[Self], CopyBeam)
            else:
                # Fall back to CopyDune for unsupported family names
                return cast(Self, super().__new__(cls))

        return cast(Self, super().__new__(cls))

    def start(
        self, job_id: str = "", ticket_id: str = "", preview_reps: int = 0
    ) -> int:
        """
        Start a copy job.
        Args:
            job_id: job id
            ticket_id: ticket id
        Returns:
            Status code of the start job. 200 for success operation.
        """
        super().preview_start(job_id, ticket_id)

        if preview_reps != 0:
            for rep in range(preview_reps):
                self._job_manager.change_job_state(
                    job_id, "Preview", "prepareProcessing"
                )
                self._job_manager.wait_for_job_state(job_id, ["ready"])
                print("Preview Job Id : {}".format(job_id))

        start_state = self.change_job_state(job_id, "Start", "startProcessing")
        return start_state
