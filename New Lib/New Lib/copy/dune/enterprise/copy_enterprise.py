import logging
from typing import Dict
import logging
import time

from dunetuf.copy.dune.copy_dune import CopyDune


class CopyEnterprise(CopyDune):
    """
    Concrete implementation of CopyDune for enterprise-based architecture.
    """

    def _updating_ticket(self, payload: Dict) -> Dict:
        """
        Update the ticket.
        Args:
            ticket: The ticket to update.
        Returns:
            None
        """
        super()._updating_ticket(payload)
        if payload.get("src", {}).get("scan", {}).get("resolution"):
            payload["src"]["scan"]["resolution"] = "e600Dpi"
        return payload

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

        time.sleep(2.5)  # Wait for the job to be ready
        #self._job_manager.wait_for_job_state(job_id, ["ready"])
        start_state = self.change_job_state(job_id, "Start", "startProcessing")

        logging.info("Waiting for job to be ready")
        adf_loaded = self._udw.mainApp.ScanMedia.isMediaLoaded('ADF') #type: ignore
        try:
            if preview_reps == 0:
                if not self._adf_loaded and self._output_duplex is True:
                    self._job_manager.wait_for_alerts("flatbedAddPage")
                    self._job_manager.alert_action(
                        "flatbedAddPage", "Response_02"
                    )  # TODO: Review this.
            elif not adf_loaded:
                self._job_manager.wait_for_alerts("flatbedAddPage")
                self._job_manager.alert_action(
                        "flatbedAddPage", "Response_02"
                    )
            else:
                logging.info("ADF is loaded, no need to add flatbed page")
        except TimeoutError:
            logging.info("flatbed Add page is not available")

        return start_state
