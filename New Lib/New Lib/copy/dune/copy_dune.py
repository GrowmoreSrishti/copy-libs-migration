import inspect
from typing import Any, Type, cast
import time
import logging

from typing_extensions import Self  # type: ignore

from dunetuf.copy.copy import Copy

class CopyDune(Copy):
    """
    Concrete implementation of Copy for Dune-based architecture.
    """

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        """
        Create a new instance of CopyDune or its subclass.
        Returns:
            An instance of CopyDune or its subclass.
        """
        if cls is CopyDune:
            caller_frame = inspect.stack()[1]
            caller_module = inspect.getmodule(caller_frame[0])
            if caller_module is None or not (
                caller_module.__name__.startswith("dunetuf.copy.copy")
            ):
                raise RuntimeError(
                    "CopyDune (and its subclasses) can only be instantiated via Copy."
                )

            if cls._family_name == "enterprise":
                from dunetuf.copy.dune.enterprise.copy_enterprise import CopyEnterprise
                return cast(Self, CopyEnterprise(*args, **kwargs))
            elif cls._family_name == "designjet":
                from dunetuf.copy.dune.designjet.copy_designjet import CopyDesignJet
                return cast(Self, CopyDesignJet(*args, **kwargs))
            elif cls._family_name == "homepro":
                from dunetuf.copy.dune.homepro.copy_homepro import CopyHomePro
                return cast(Self, CopyHomePro(*args, **kwargs))
            else:
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
        self.preview_start(job_id, ticket_id, preview_reps)
        if preview_reps == 0:
            start_state = self.change_job_state(job_id, 'Start', 'startProcessing')
            return start_state

        time.sleep(2.5)  # Wait for the job to be ready
        start_state = self.change_job_state(job_id, "Start", "startProcessing")

        logging.info("Waiting for job to be ready")
        adf_loaded = self._udw.mainApp.ScanMedia.isMediaLoaded('ADF') #type: ignore
        try:
            if not adf_loaded:
                self._job_manager.wait_for_alerts("flatbedAddPage")
                self._job_manager.alert_action(
                        "flatbedAddPage", "Response_02"
                    )
            else:
                logging.info("ADF is loaded, no need to add flatbed page")
        except TimeoutError:
            logging.info("flatbed Add page is not available")

        return start_state

    def preview_start(self, job_id: str, ticket_id: str, preview_reps: int = 0) -> None:
        """
        Start a copy job.
        Args:
            job_id: job id
            ticket_id: ticket id
            preview_reps: Number of times to repeat the preview before executing the copy job
        Returns:
            None
        """
        super().preview_start(job_id, ticket_id)
        if preview_reps != 0:
            for _ in range(preview_reps):
                self._job_manager.change_job_state(
                    job_id, "Preview", "prepareProcessing"
                )
                time.sleep(2.5)
                self._job_manager.wait_for_job_state(job_id, ["ready"])
                logging.info("Preview Job Id : {}".format(job_id))
