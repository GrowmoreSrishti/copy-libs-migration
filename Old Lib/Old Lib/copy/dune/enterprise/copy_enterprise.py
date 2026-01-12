import logging
from typing import Dict

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
        super().preview_start(job_id, ticket_id)

        if preview_reps != 0:
            for rep in range(preview_reps):
                self._job_manager.change_job_state(
                    job_id, "Preview", "prepareProcessing"
                )
                self._job_manager.wait_for_job_state(job_id, ["ready"])
                print("Preview Job Id : {}".format(job_id))

        start_state = self.change_job_state(job_id, "Start", "startProcessing")

        try:
            if not self._adf_loaded and self._output_duplex is True:
                self._job.wait_for_alerts("flatbedAddPage")
                self._job.alert_action(
                    "flatbedAddPage", "Response_02"
                )  # TODO: Review this.
        except TimeoutError:
            logging.info("flatbed Add page is not available")

        return start_state
