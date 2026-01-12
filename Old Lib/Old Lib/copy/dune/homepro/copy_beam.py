from dunetuf.copy.dune.homepro.copy_homepro import CopyHomePro


class CopyBeam(CopyHomePro):
    """
    Concrete implementation of CopyBeam for homepro-based architecture.
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
        start_state = super().start(job_id, ticket_id, preview_reps)
        self.dismiss_mdf_eject_page_alert()

        return start_state
