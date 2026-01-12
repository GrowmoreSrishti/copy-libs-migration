from dunetuf.copy.dune.copy_dune import CopyDune
import time
import logging


class CopyDesignJet(CopyDune):
    """
    Concrete implementation of CopyDune for desingjet-based architecture.
    """

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

        if ticket_id != "" and self._has_two_segment_pipeline(ticket_id):
            status_code = self._job_manager.change_job_state(
                job_id, "Prepare_Processing", "prepareProcessing"
            )
            assert status_code == 200
            self.wait_for_state(job_id, ["processing"])
            
            result = self._job_manager.wait_for_all_previews_done(job_id)
            assert result, "Preview jobs did not finish successfully"
            
            if self.get_copy_configuration()["copyMode"] == "printWhileScanning":
                logging.info("Copy mode is already set to printWhileScanning. Wait for start print to finish job.")
                self._job_manager.wait_for_job_processing_sub_status(status="printing")

        start_state = self.change_job_state(job_id, "Start", "startProcessing")
        return start_state
