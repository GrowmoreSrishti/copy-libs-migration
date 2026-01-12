###############################################################################
#  @file   copy.py
#  @author Anu Sebastian (anu.sebastian@hp.com)
#  @date   05-10-2020
#  @brief  Python implementation for copy operation on simulator/emulator/engine.
#
#  (c) Copyright HP Inc. 2019. All rights reserved.
###############################################################################
import time
import copy
from time import ctime
from typing import Dict, List, Optional, Any, Type, cast
from typing_extensions import Self # type: ignore
from typing import ClassVar, Dict, List
from enum import Enum

from dunetuf.cdm import CDM, get_cdm_instance
from dunetuf.cdm.CdmEndpoints import CdmEndpoints
from dunetuf.udw import DuneUnderware, get_dune_underware_instance
from dunetuf.ssh import SSH
from dunetuf.job.job import Job
from dunetuf.scan.ScanAction import ScanSimMode
import dunetuf.common.commonActions as CommonActions
import logging
from dunetuf.configuration import Configuration
from dunetuf.metadata import get_ip
from dunetuf.job._job_manager.job_manager import JobManager
from dunetuf.job._job_manager.job_manager import JobState
from dunetuf.job._job_manager.job_manager import ResourceService
from dunetuf.job._job_ticket.job_ticket import JobTicket
from dunetuf.job.job_configuration.job_configuration import JobConfiguration
from dunetuf.common.base.abstract_job_actions import AbstractJobActions

Cancel = Enum('Cancel', 'no after_init after_start after_create submit_and_exit submit_preview_and_exit after_preview') #TODO: REMOVE

class Copy(AbstractJobActions):
    """
    A class for dealing with copy operations on simulator/emulator/engine
    """

    def __new__(cls: Type[Self], *args: Any, **kwargs: Any) -> Self:
        """
        Create a new instance of Copy or its subclass.
        """
        if cls is Copy:
            ip_address = get_ip()
            cls._udw = get_dune_underware_instance(ip = ip_address)          
            cls._cdm = get_cdm_instance(addr = ip_address, udw = cls._udw)
            cls._configuration = Configuration(cls._cdm)
            cls._family_name = cls._configuration.familyname
            cls._product_name = cls._configuration.productname
            # TODO - Implement Ares copy class
            from dunetuf.copy.dune.copy_dune import \
                CopyDune
            cls = cast(Type[Self], CopyDune)

        return cast(Self, super().__new__(cls))
    
    def __init__(self, cdm: Optional[CDM] = None, udw: Optional[DuneUnderware] = None):
        """
        Initialize the Copy class.
        
        This constructor sets up all necessary instances for managing copy operations
        on supported devices. It initializes connections to the device's control data
        manager (CDM) and underware interface, as well as various job-related objects.
        
        Args:
            cdm: Optional CDM instance. If not provided, one will be created automatically.
            udw: Optional DuneUnderware instance. If not provided, one will be created automatically.
        """
        # Get the device IP address
        ip_address = get_ip()
        
        # Initialize underware and CDM interfaces, using provided instances or creating new ones
        self._udw = udw if udw is not None else get_dune_underware_instance(ip=ip_address)
        self._cdm = cdm if cdm is not None else get_cdm_instance(addr=ip_address, udw=self._udw)
        
        # Initialize job management objects
        self._job: Job = Job(self._cdm, self._udw)
        self._job_manager = JobManager()
        self._job_ticket = JobTicket()
        self._job_configuration = JobConfiguration()
        
        # Initialize device configuration and properties
        self._configuration = Configuration(self._cdm)
        self._family_name = self._configuration.familyname
        
        # Initialize state variables with None (will be set during copy operations)
        self._adf_loaded = None
        self._output_duplex = None
        self._duplex = None

    def create_ticket(self, payload: Dict, passwords: str = '', headers=None) -> str:
        """
        Creates a copy job ticket with the provided settings.
        Args:
            payload (Dict): Dictionary variable to set various copy job parameters.
            passwords (str, optional): Passwords required for the job. Defaults to ''.
            headers (optional): Additional headers for the job request. Defaults to None.
        Returns:
            str: The generated job ticket id.
        """

        self._updating_ticket(payload)
        base_payload = {'src' : {'scan': {}}, 'dest' : {'print':{}}}
        ticket_id = self._job_ticket.create(base_payload)


        logging.info('Payload copy job ticket : {}'.format(payload))
        self._job_ticket.update(ticket_id, payload)

        return ticket_id

    def create_job(self, ticketId: str, autostart: bool = False, priorityModeSessionId: str = "", headers=None) -> str:
        """
        Creates a copy job with the provided ticket.
        Args:
            ticketId (str): Job's ticket id for which a job should be created.
            autostart (bool, optional): Whether to automatically start the job. Defaults to False.
            priorityModeSessionId (str, optional): The session ID for priority mode. Defaults to an empty string.
            headers (dict, optional): Additional headers to include in the request. Defaults to None.
        Returns:
            str: The created job id.
        """
        job_id = self._job_manager.create_job(ticketId, autostart, priorityModeSessionId, headers)
        return job_id

    def get_job_info(self, jobid: str, header = None) -> Dict:
        """
        Connects to printer and gets specific jobs details based on jobID.
        Args:
            jobid: Job identifier, CDM (str) representation
        Returns:
            Dict containing job status
        """
        return self._job_manager.get_job_info(jobid, header)

    def change_job_state(self, jobID: str, action: str, jobState: str, header = None) -> int:
        """
        Change a job's state.
        Args:
            jobID: Job id
            action: String stating the action
            jobState: Job state. Possible values are [startProcessing, initializeProcessing, cancelProcessing, pauseProcessing, resumeProcessing]
        Returns:
            Status code
        """
        return self._job_manager.change_job_state(jobID, action, jobState, header)


    def start(self, job_id: str = "", ticket_id: str = "", preview_reps: int = 0) -> int:
        """
        Start a copy job.
        Args:
            job_id: job id
            ticket_id: ticket id
            preview_reps: Number of times to repeat the preview before executing the copy job
        Returns:
            Status code of the start job. 200 for success operation.
        """
        self.preview_start(job_id, ticket_id)

        start_state = self.change_job_state(job_id, 'Start', 'startProcessing')
        return start_state

    def preview_start(self, job_id: str, ticket_id: str) -> None:
        """
        Start a copy job.
        Args:
            job_id: job id
            ticket_id: ticket id
        Returns:
            Status code of the start job. 200 for success operation.
        """
        logging.info('Starting job : %s', job_id)
        job_ready = False

        initialize_pending_state = self._job_manager.change_job_state(job_id, 'Initialize', 'initializeProcessing')
        assert initialize_pending_state == 200

        start_time = time.time()

        while((time.time() - start_time) < self._job_manager.WAIT_START_JOB_TIMEOUT):
            job_info = self.get_job_info(job_id)
            if job_info.get('state') == 'ready':
                job_ready = True
                break
            else:
                time.sleep(2)
        if not job_ready:
            raise TimeoutError("Job has not reached the ready state after {0} seconds".format(self._job_manager.WAIT_START_JOB_TIMEOUT))

    def cancel(self, jobId: str, header = None) -> int:
        """
        Cancels a copy job.
        Args:
            jobId: job id
        Returns:
            Status code of the cancel request. 200 for success operation.
        """
        return self._job_manager.cancel_job(jobId, header)

    def get_user_ticket_defaults(self) -> Dict:
        """
        Get the user defaults job tickets for copy.
        Args:
            None
        Returns:
            Dict containing the user defaults for job tickets by type.
        """
        return self._job_ticket.get_user_defaults_type('copy')

    def get_user_ticket_defaults_constraints(self) -> Dict:
        """
        Get the user defaults constraints for copy.
        Args:
            None
        Returns:
            Dict containing the user defaults constraints for job tickets by type.
        """
        return self._job_ticket.get_user_defaults_constraints_type('copy')

    def wait_for_state(self, jobid: str, final_states: List[str]) -> str: 
        """Wait for the job to reach one of the final states.
        Args:
            jobid: wait for this job to reach one of the final states
            timeout: timeout in seconds to wait for job completion
            final_states: list of final states to wait for
        Returns:
            jobstate string
        Raises:
            TimeoutError if no new jobs are found within ``timeout`` seconds
        """
        return self._job_manager.wait_for_job_state(jobid, final_states)

    def register_job_manager_events(self) -> None:
        """Register job manager events.
        Args:
            None
        Returns:
            None
        """
        self._job_manager.register_job_manager_events()

    def get_default_ticket(self) -> Dict:
        """
        Get the default copy job ticket.
        Args:
            None
        Returns:
            Dict containing the default copy job ticket.
        """
        return self._job_ticket.get_configuration_defaults_by_type('copy')

    def update_default_ticket(self, payload: Dict) -> int:
        """
        Update the default copy job ticket.
        Args:
            payload: Dictionary containing the updated job ticket information.
        Returns:
            Dict containing the updated default copy job ticket.
        """
        return self._job_ticket.update_configuration_defaults_by_type('copy', payload)

    def _updating_ticket(self, payload: Dict) -> Dict:
        """
        Updates the ticket payload with specific scan and print settings based on the provided payload.
        Args:
            payload (Dict): The dictionary containing the ticket information to be updated. 
                            It may contain 'src' and 'dest' keys with nested dictionaries.
        Returns:
            Dict: The updated payload dictionary with modified scan and print settings.
        Updates:
            - If 'src' key is present in the payload:
                - Sets `adfLoaded` to False if 'mediaSource' in 'src' is "flatbed".
                - Sets `duplex` to True if 'plexMode' in 'src' is "duplex".
            - If 'dest' key is present in the payload:
                - Sets `output_duplex` to True if 'plexMode' in 'dest' is "duplex".
                - Sets 'duplexBinding' in 'dest' to "twoSidedLongEdge" if it is "oneSided" or not present.
        """ 
        if "src" in payload:
            if "mediaSource" in payload['src']['scan']:
                if payload['src']['scan']['mediaSource'] == "flatbed":
                    self._adf_loaded = False
            if "plexMode" in payload['src']['scan']:
                if payload['src']['scan']['plexMode'] == "duplex":
                    self._duplex = True
        if "dest" in payload:
            if "plexMode" in payload['dest']['print']:
                if payload['dest']['print']['plexMode'] == "duplex":
                    self._output_duplex = True
                    if "duplexBinding" in payload['dest']['print']:
                        if payload['dest']['print']['duplexBinding'] == "oneSided":
                            payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge"
                    else:
                        payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge" 

        return payload

    def _has_two_segment_pipeline(self, ticket_id) -> bool:
        """
        Check wether a printer has two segments pipeline
        """
        try:
            data = self._job_ticket.get_info(ticket_id)
            field_value = data['src']['scan']['scanCaptureMode']
            return field_value == 'jobBuild'
        except:
            return False

    def _dismiss_mdf_eject_page_alert(self) -> None: #TODO: TAKE A LOOK IF IT IS NECESSARY if "mdf" in self._udw.mainApp.ScanMedia.listInputDevices().lower() and self._udw.mainUiApp.ControlPanel.getBreakPoint() not in ["XL"]: 
        """
        This headless method is to dismiss mdfEjectPage alert when perform copy on MDF
        """
        logging.info("Try to dismiss_mdf_eject_page_alert")
        alert_detail = self._cdm.alerts.wait_for_alerts("mdfEjectPage")[0]
        url = alert_detail["actions"]["links"][0]["href"]
        action_value = alert_detail["actions"]["supported"][0]["value"]["seValue"]
        self._cdm.put(url, {"jobAction" : action_value})

    def get_copy_configuration(self) -> Dict: 
        """
        Get copy configuration
        Returns:
            Dict containing the copy configuration
        """
        return self._cdm.get(self._cdm.COPY_CONFIGURATION_ENDPOINT)

    def set_copy_configuration(self, payload: Dict) -> None:
        """
        Set copy configuration
        Args:
            payload: Dictionary containing the copy configuration to set
        Returns:
            None
        """
        self._cdm.put(self._cdm.COPY_CONFIGURATION_ENDPOINT, payload)

    
    def do_preview_job(self, waitTime: int=60, **payload: Dict) -> str:
        """Configures a copy job and performs preview on copy job

        Args:
            waitTime: Timeout in seconds to check for copy job state. Defaults to 60
            payload: Dictionary variable to set various copy job parameters

        Returns:
            ticket_id
        """
        logging.info('\n========== COPY Job Started ==========')
        max_wait_time = waitTime
               
        payload = self._updating_ticket(payload) 

        ticket_id = self.create_ticket(payload)
        job_id = self.create_job(ticket_id)
        logging.info('Created Copy Job Id : {}'.format(job_id))

        self._job.check_job_state(job_id, 'created', max_wait_time)
        self.change_job_state(job_id, 'Initialize', 'initializeProcessing')

        self._job.check_job_state(job_id, 'ready', max_wait_time)
        # for rep in range(reps):  
        self._job.change_job_state(job_id, 'Preview', 'prepareProcessing')
        return ticket_id

    '''
    ==================================================================================
    WARNING: DEPRECATED METHODS BELOW
    
    All methods below are OUTDATED and SHOULD NOT BE USED in new code.
    They are kept for backward compatibility only.
    
    Please use the newer methods defined above instead.
    ==================================================================================
    '''

    def get_copy_job_ticket(self, payload: Dict) -> str:
        """Creates a copy job ticket with the provided settings.

        Args:
            payload: Dictionary variable to set various copy job parameters

        Returns:
            Returns the generated job ticket id
        """
        base_payload = {'src' : {'scan': {}}, 'dest' : {'print':{}}}
        ticket_id = self._job.create_job_ticket(base_payload)

        if bool(payload):
            print('Payload copy job ticket : {}'.format(payload))
            self._job.update_job_ticket(ticket_id, payload)

        data = self._job.get_job_ticket_info(ticket_id)
        print('Ticket ID - {}, Ticket Info - {}'.format(ticket_id, data))

        return ticket_id

    def has_two_segment_pipeline(self, ticket_id):
        """
        Check wether a printer has two segments pipeline
        """
        try:
            data = self._job.get_job_ticket_info(ticket_id)
            field_value = data['src']['scan']['scanCaptureMode']
            return field_value == 'jobBuild'
        except:
            return False

    def proccess_job_two_segment_completion_check(self, job_id, cancel: Cancel=Cancel.no, waitTime: int=60  ):
        """
        Proccess a two segment pipeline job and check for successul completion

        Args:
            job_id : job's id
            cancel : desired cancel action
            waitTime : time to wait for the action to be completed
        """
        status_code = self._job.change_job_state(job_id, 'Prepare_Processing', 'prepareProcessing')
        self._job.check_job_state(job_id, "processing", 30)

        if cancel == Cancel.submit_preview_and_exit:
            return
        
        self._job.wait_all_previews_done(job_id)

        # Patch start processing to start second segment 
        self._job.change_job_state(job_id, 'Start', 'startProcessing')

        it_was_canceled = False
        expected_completion_status = "success"
        # Can be cancelled after start, check it
        if cancel == Cancel.after_start:
            it_was_canceled = True
            expected_completion_status = "cancelled"
            self._job.cancel_job(job_id)
            print('Canceled Job Id : {}'.format(job_id))
            # Wait completion status and validate is completed

        if cancel == Cancel.submit_and_exit:
            print('Submitted Copy Job with Id: ' + job_id +  ' .Track it to completion.')
        else:
            # Wait completion status and validate is completed
            self._job.check_job_state(job_id, 'completed', waitTime, it_was_canceled)

            # Get status job
            self._job.check_job_completion_status(job_id,expected_completion_status)

    def do_copy_job(self, familyname= "", adfLoaded = True, cancel: Cancel=Cancel.no, waitTime: int=60, priorityModeSessionId: str = "", **payload: Dict) -> str:
        """Configures a copy job and performs copy job

        Args:
            cancel: Possible values are ['no', 'after_init', 'after_start', 'after_create']
                    that specifies the post action after starting the copy job.
                    Defaults to 'no'
            waitTime: Timeout in seconds to check for copy job state. Defaults to 60
            payload: Dictionary variable to set various copy job parameters

        Returns:
            Return the jobid
        """
        print('\n========== COPY Job Started ==========')

        _ssh = SSH(self._cdm.ipaddress)
        max_wait_time = waitTime
        self.configuration = Configuration(self._cdm)
        input_duplex = False
        output_duplex = False

        
        if familyname == '':
            try:
                familyname = self.configuration.familyname
            except:
                logging.info("There is no information about the device.")
 
        if "src" in payload:
            if "mediaSource" in payload['src']['scan']:
                if payload['src']['scan']['mediaSource'] == "flatbed":
                    adfLoaded = False
            if "plexMode" in payload['src']['scan']:
                if payload['src']['scan']['plexMode'] == "duplex":
                    duplex = True
            if "resolution" in payload['src']['scan']:
                if familyname == "enterprise":
                    payload['src']['scan']['resolution'] = "e600Dpi" 
        if "dest" in payload:
            if "plexMode" in payload['dest']['print']:
                if payload['dest']['print']['plexMode'] == "duplex":
                    output_duplex = True
                    if "duplexBinding" in payload['dest']['print']:
                        if payload['dest']['print']['duplexBinding'] == "oneSided":
                            payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge"
                    else:
                        payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge"   

        ticket_id = self.get_copy_job_ticket(payload)
          
        job_id = self._job.create_job(ticket_id, priorityModeSessionId=priorityModeSessionId)
        print('Created Copy Job Id : {}'.format(job_id))
         
        if cancel == Cancel.after_create:
            self._job.cancel_job(job_id)

            jobs = self._job.get_job_history()
            job_in_history = [job for job in jobs if job.get('jobId') == job_id]
            assert len(job_in_history) == 0, 'Unexpected job in job history!'

            print('Canceled Job Id : {}'.format(job_id))
        else:
            self._job.check_job_state(job_id, 'created', max_wait_time)
            self._job.change_job_state(job_id, 'Initialize', 'initializeProcessing')
            print('Initialized Job Id : {}'.format(job_id))
            if cancel == Cancel.after_init:
                self._job.cancel_job(job_id)

                jobs = self._job.get_job_history()
                job_in_history = [job for job in jobs if job.get('jobId') == job_id]
                assert len(job_in_history) == 0, 'Unexpected job in job history!'

                print('Canceled Job Id : {}'.format(job_id))
            else:
                self._job.check_job_state(job_id, 'ready', max_wait_time) 
                # Check for a product with two segment pipeline
                if (self.has_two_segment_pipeline(ticket_id)):
                    print("********* Two segment pipeline detected **********")
                    print(" ## cancel =", cancel)
                    self.proccess_job_two_segment_completion_check(job_id, cancel, waitTime)
                else:          
                    self._job.change_job_state(job_id, 'Start', 'startProcessing')
                    print('Started Job Id : {}'.format(job_id))
                    #Pages currently set to 1 can be changed if required in future through argument
                    if familyname == "enterprise" :
                        try:
                            if adfLoaded == False and output_duplex == True:
                                self._job.wait_for_alerts('flatbedAddPage')
                                self._job.alert_action('flatbedAddPage', 'Response_02')
                        except TimeoutError:
                            logging.info("flatbed Add page is not available")

                    if cancel == Cancel.after_start:
                        self._job.cancel_job(job_id)
                        self._job.check_job_state(job_id, 'completed', max_wait_time, True)
                        print('Canceled Job Id : {}'.format(job_id))
                    else :
                        if cancel == Cancel.submit_and_exit: #reusing cancel parameter to submit job and exit without waiting for completion
                            print('Submitted Copy Job with Id: ' + job_id +  ' .Track it to completion.')
                        else:
                            # Due to recent change in check_job_state(introduced a sleep), during which processing state move to completed
                            #self._job.check_job_state(job_id, 'processing', max_wait_time)
                            #print('started processing the copy job..')
                            if "mdf" in self._udw.mainApp.ScanMedia.listInputDevices().lower() and self._udw.mainUiApp.ControlPanel.getBreakPoint() not in ["XL"]:
                                self.dismiss_mdf_eject_page_alert()
                            self._job.check_job_state(job_id, 'completed', max_wait_time)
                            print('Completed Job Id : {}'.format(job_id))

        print('========== COPY Job Completed ==========')

        print('Copy Job completed. Removing possible generated output file.')
        _ssh.run('rm -f /tmp/PUID_*.tiff')
        return job_id
    
    def do_copy_preview_job(self, familyname = "", cancel: Cancel=Cancel.no, waitTime: int=60, reps: int=0, onlypreview: bool=False, **payload: Dict) -> None:
        """Configures a copy job and performs copy job

        Args:
            cancel: Possible values are ['no', 'after_init', 'after_start', 'after_create']
                    that specifies the post action after starting the copy job.
                    Defaults to 'no'
            waitTime: Timeout in seconds to check for copy job state. Defaults to 60
            reps: Repetitions, the number of times to repeat the preview before executing the copy job
            payload: Dictionary variable to set various copy job parameters

        Returns:
            None
        """
        print('\n========== COPY Job Started ==========')
        _ssh = SSH(self._cdm.ipaddress)
        max_wait_time = waitTime
        self.configuration = Configuration(self._cdm)
        
        if familyname == '':
            try:
                familyname = self.configuration.familyname
            except:
                logging.info("There is no information about the device.")
               
        if "src" in payload:
            if "mediaSource" in payload['src']['scan']:
                if payload['src']['scan']['mediaSource'] == "flatbed":
                    adfLoaded = False
            if "plexMode" in payload['src']['scan']:
                if payload['src']['scan']['plexMode'] == "duplex":
                    duplex = True
            if "resolution" in payload['src']['scan']:
                if familyname == "enterprise":
                    payload['src']['scan']['resolution'] = "e600Dpi" 
        if "dest" in payload:
            if "plexMode" in payload['dest']['print']:
                if payload['dest']['print']['plexMode'] == "duplex":
                    if "duplexBinding" in payload['dest']['print']:
                        if payload['dest']['print']['duplexBinding'] == "oneSided":
                            payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge"
                    else:
                        payload['dest']['print']['duplexBinding'] = "twoSidedLongEdge" 

        ticket_id = self.get_copy_job_ticket(payload)
        job_id = self._job.create_job(ticket_id)
        print('Created Copy Job Id : {}'.format(job_id))

        if cancel == Cancel.after_create:
            self._job.cancel_job(job_id)

            jobs = self._job.get_job_history()
            job_in_history = [job for job in jobs if job.get('jobId') == job_id]
            assert len(job_in_history) == 0, 'Unexpected job in job history!'

            print('Canceled Job Id : {}'.format(job_id))
        else:
            self._job.check_job_state(job_id, 'created', max_wait_time)
            self._job.change_job_state(job_id, 'Initialize', 'initializeProcessing')
            print('Initialized Job Id : {}'.format(job_id))

            if cancel == Cancel.after_init:
                self._job.cancel_job(job_id)

                jobs = self._job.get_job_history()
                job_in_history = [job for job in jobs if job.get('jobId') == job_id]
                assert len(job_in_history) == 0, 'Unexpected job in job history!'

                print('Canceled Job Id : {}'.format(job_id))
            else:
                self._job.check_job_state(job_id, 'ready', max_wait_time)
                for rep in range(reps):  
                    self._job.change_job_state(job_id, 'Preview', 'prepareProcessing')
                    self._job.check_job_state(job_id, 'ready', max_wait_time)
                    print('Preview Job Id : {}'.format(job_id))
                else:
                    print('Previewed job {} times'.format(reps))           

                if cancel == Cancel.after_preview:
                        self._job.cancel_job(job_id)

                        jobs = self._job.get_job_history()
                        job_in_history = [job for job in jobs if job.get('jobId') == job_id]
                        assert len(job_in_history) == 0, 'Unexpected job in job history!'

                        print('Canceled Job Id : {}'.format(job_id))
                else:
                    self._job.check_job_state(job_id, 'ready', max_wait_time)
                    self._job.change_job_state(job_id, 'Start', 'startProcessing')
                    print('Started Job Id : {}'.format(job_id))
                    adfLoaded = self._udw.mainApp.ScanMedia.isMediaLoaded('ADF')
                    #Pages currently set to 1 can be changed if required in future through argument
                    pages = 1
                    
                    try:
                        if adfLoaded == False:
                            for number in range(pages-1):
                                self._job.wait_for_alerts('flatbedAddPage')
                                self._job.alert_action('flatbedAddPage', 'Response_01')
                            self._job.wait_for_alerts('flatbedAddPage')
                            self._job.alert_action('flatbedAddPage', 'Response_02')
                    except TimeoutError:
                        logging.info("flatbed Add page is not available")

                    if cancel == Cancel.after_start:
                        self._job.cancel_job(job_id)
                        self._job.check_job_state(job_id, 'completed', max_wait_time, True)
                        print('Canceled Job Id : {}'.format(job_id))
                    else :
                        if cancel == Cancel.submit_and_exit: #reusing cancel parameter to submit job and exit without waiting for completion
                            print('Submitted Copy Job with Id: ' + job_id +  ' .Track it to completion.')
                        else:
                            # Due to recent change in check_job_state(introduced a sleep), during which processing state move to completed
                            #self._job.check_job_state(job_id, 'processing', max_wait_time)
                            #print('started processing the copy job..')
                            self._job.check_job_state(job_id, 'completed', max_wait_time)
                            print('Completed Job Id : {}'.format(job_id))

        print('========== COPY Job Completed ==========')

        print('Copy Job completed. Removing possible generated output file.')
        _ssh.run('rm -f /tmp/PUID_*.tiff')
    
    def start_copy_job(self, waitTime: int=60, **payload: Dict) -> str:
        """Configures a copy job and starts copy job
        
        Args:
            waitTime: Timeout in seconds to check for copy job state. Defaults to 60
            payload: Dictionary variable to set various copy job parameters

        Returns:
            Job id, for use in checking for completioin
        """
        print('\n========== COPY Job Started ==========')
        ticket_id = self.get_copy_job_ticket(payload)

        _ssh = SSH(self._cdm.ipaddress)
        max_wait_time = waitTime

        job_id = self._job.create_job(ticket_id)
        print('Created Copy Job Id : {}'.format(job_id))
        self._job.check_job_state(job_id, 'created', max_wait_time)
        self._job.change_job_state(job_id, 'Initialize', 'initializeProcessing')
        print('Initialized Job Id : {}'.format(job_id))
        self._job.check_job_state(job_id, 'ready', max_wait_time)           
        self._job.change_job_state(job_id, 'Start', 'startProcessing')
        print('Started Job Id : {}'.format(job_id))
        self._job.check_job_state(job_id, 'processing', max_wait_time)
        print('started processing the copy job..')
        return job_id

    def validate_settings_used_in_copy(self, original_size=None, paper_size=None, lighter_darker=None,
                                        output_scale_setting=None, number_of_copies: int = None, blank_page_suppression=None,
                                        color_mode=None, tray_setting=None, sides=None, orientation=None,
                                        quality=None, copy_margins=None,content_type=None, two_side_page_flip_up=None,
                                        pages_per_sheet=None, collate=None, media_source=None, input_plex_mode=None, output_scale_standard_size_setting=None, output_scale_loaded_paper_setting=None,
                                        finisher_staple=None, finisher_punch=None, numberUp_presentation_direction=None, image_border=None, finisher_fold=None,
                                        booklet_format=None, output_plex_mode=None, finisher_booklet=None, watermark_type=None, watermark_Id=None, watermark_custom_text=None,
                                        watermark_first_page_only=None, watermark_text_font=None, watermark_text_size=None, watermark_text_color=None, watermark_darkness=None,
                                        stamp_location=None, stamp_location_id=None, stamp_policy=None, stamp_content=None, stamp_text_color=None, stamp_text_font=None,
                                        stamp_text_size=None, stamp_starting_page=None, stamp_starting_number=None, stamp_num_of_digit=None, stamp_page_numbering=None, stamp_white_background=None) -> None:
        """
        Verify all the settings used for copy job using cdm
        :param job:
        :param original_size:
        :param paper_size:
        :param lighter_darker:
        :param output_scale_setting:
        :param number_of_copies:
        :param color_mode:
        :param tray_setting:
        :param sides:
        :param orientation:
        :param quality:
        :param copy_margins:
        :param content_type:
        :param two_side_page_flip_up:
        :param pages_per_sheet:
        :param collate:
        :param media_source:
        :param input_plex_mode:
        :param finisher_staple:
        :param finisher_punch:
        :param booklet_format:
        :param output_plex_mode:
        :param finisher_booklet:
        :param watermark_type:
        :param watermark_Id:
        :param watermark_custom_text:
        :param watermark_first_page_only:
        :param watermark_text_font:
        :param watermark_text_size:
        :param watermark_text_color:
        :param watermark_darkness:
        :param stamp_location:
        :param stamp_location_id:
        :param stamp_policy:
        :param stamp_content:
        :param stamp_text_color:
        :param stamp_text_font:
        :param stamp_text_size:
        :param stamp_starting_page:
        :param stamp_starting_number:
        :param stamp_num_of_digit:
        :param stamp_page_numbering:
        :param stamp_white_background:
        """
        logging.info("Verify all the values used for job using cdm")
        copy_job_details = self._job.get_job_details(current_job_type="copy")

        if original_size:
            logging.info("Check the original size setting")
            assert copy_job_details["src"]["scan"]["mediaSize"] == original_size, "Wrong original size setting"

        if paper_size:
            logging.info("Check the paper size setting")
            assert copy_job_details["dest"]["print"]["mediaSize"] == paper_size, "Wrong paper size setting"

        if lighter_darker:
            logging.info("Check the lighter/darker setting")
            assert copy_job_details["pipelineOptions"]["imageModifications"][
                    "exposure"] == lighter_darker, "Wrong lighter/darker setting"

        if output_scale_setting:
            logging.info("Check the output scale setting")
            scaling_dict = copy_job_details["pipelineOptions"]["scaling"]
            assert scaling_dict.get("scaleToFitEnabled") == output_scale_setting.get(
                "scaleToFitEnabled") and scaling_dict.get("xScalePercent") == output_scale_setting.get(
                "yScalePercent") and scaling_dict.get("scaleSelection") == output_scale_setting.get("scaleSelection")

        if number_of_copies:
            logging.info("Check the number of copies")
            assert copy_job_details["dest"]["print"]["copies"] == number_of_copies, "Wrong number of copies"
            
        if blank_page_suppression:
            logging.info("Check the blank page suppression")
            assert copy_job_details["pipelineOptions"]["imageModifications"]["blankPageSuppressionEnabled"] == blank_page_suppression, "Wrong blank page suppression"   

        if color_mode:
            logging.info("Check the color mode")
            assert copy_job_details["src"]["scan"]["colorMode"] == color_mode, "Wrong color mode"

        if tray_setting:
            logging.info("Check the tray setting")
            assert copy_job_details["dest"]["print"]["mediaSource"] == tray_setting, "Wrong tray setting"

        if sides:
            logging.info("Check the sides")
            assert copy_job_details["dest"]["print"]["duplexBinding"] == sides

        if orientation:
            logging.info("Check the orientation")
            assert copy_job_details["src"]["scan"]["contentOrientation"] == orientation, "Wrong orientation"

        if quality:
            logging.info("Check the quality")
            assert copy_job_details["dest"]["print"]["printQuality"] == quality, "Wrong quality"

        if copy_margins:
           logging.info("Check the copy margins")
           assert copy_job_details["dest"]["print"]["printMargins"] == copy_margins, "Wrong copy margins"

        if content_type:
            logging.info("Check the content type")
            assert copy_job_details["src"]["scan"]["contentType"] == content_type, "Wrong content type"

        if two_side_page_flip_up:
            logging.info("Check 2 side page flip up")
            assert copy_job_details["src"]["scan"][
                    "pagesFlipUpEnabled"] == two_side_page_flip_up, "Wrong 2 side page flip up"

        if pages_per_sheet:
            logging.info("Check page per sheet")
            assert copy_job_details["pipelineOptions"]["imageModifications"][
                    "pagesPerSheet"] == pages_per_sheet, "Wrong pages per sheet"
        
        if numberUp_presentation_direction:
            logging.info("Check numberUp presentation direction")
            assert copy_job_details["pipelineOptions"]["imageModifications"][
                    "numberUpPresentationDirection"] == numberUp_presentation_direction, "Wrong numberUp presentation direction"
        
        if image_border:
            logging.info("Check image border")
            assert copy_job_details["pipelineOptions"]["imageModifications"][
                    "imageBorder"] == image_border, "Wrong image border"

        if collate:
            logging.info("Check the collate")
            assert copy_job_details["dest"]["print"]["collate"] == collate, "Wrong collate"
        
        if media_source:
            logging.info("Check media source")
            assert copy_job_details['src']['scan']['mediaSource'] == media_source, "Wrong Media Source"
        
        if input_plex_mode:
            logging.info("Check media source")
            assert copy_job_details['src']['scan']['plexMode'] == input_plex_mode, "Wrong Media Source"

        if output_scale_standard_size_setting:
            logging.info("Check Output Scale Standard Size Setting")
            assert copy_job_details["pipelineOptions"]["scaling"]["scaleToSize"] == output_scale_standard_size_setting, "Wrong Standard Size"

        if output_scale_loaded_paper_setting:
            logging.info("Check Output Scale Output Scale Setting")
            assert copy_job_details["pipelineOptions"]["scaling"]["scaleToOutput"] == output_scale_loaded_paper_setting, "Wrong Loaded Paper"

        if finisher_staple:
            logging.info("Check staple Setting")
            assert copy_job_details["dest"]["print"]["stapleOption"] == finisher_staple, "Wrong staple option"

        if finisher_punch:
            logging.info("Check punch Setting")
            assert copy_job_details["dest"]["print"]["punchOption"] == finisher_punch, "Wrong punch option"

        if finisher_fold:
            logging.info("Check fold Setting")
            assert copy_job_details["dest"]["print"]["foldOption"] == finisher_fold, "Wrong fold option"
        
        if booklet_format:
            logging.info("Check image border")
            assert copy_job_details["pipelineOptions"]["imageModifications"][
                    "bookletFormat"] == booklet_format, "Wrong booklet format"
        
        if output_plex_mode:
            logging.info("Check media source")
            assert copy_job_details['dest']['print']['plexMode'] == output_plex_mode, "Wrong Media Source"

        if finisher_booklet:
            logging.info("Check bookletmaker Setting")
            assert copy_job_details["dest"]["print"]["bookletMakerOption"] == finisher_booklet, "Wrong bookletMaker option"

        if watermark_type:
            logging.info("Check watermark type Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["watermarkType"] == watermark_type, "Wrong watermark type" 

        if watermark_Id:
            logging.info("Check watermark text Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["watermarkId"] == watermark_Id, "Wrong watermark text"
        
        if watermark_custom_text:
            logging.info("Check watermark custom text Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["customText"] == watermark_custom_text, "Wrong watermark custom text"
        
        if watermark_first_page_only:
            logging.info("Check watermark first page only Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["onlyFirstPage"] == watermark_first_page_only, "Wrong watermark first page only"

        if watermark_text_font:
            logging.info("Check watermark text font Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["textFont"] == watermark_text_font, "Wrong watermark text font"

        if watermark_text_size:
            logging.info("Check watermark text size Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["textSize"] == watermark_text_size, "Wrong watermark text size"

        if watermark_text_color:
            logging.info("Check watermark text color Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["textColor"] == watermark_text_color, "Wrong watermark text color"

        if watermark_darkness:
            logging.info("Check watermark darkness Setting")
            assert copy_job_details["pipelineOptions"]["watermark"]["darkness"] == watermark_darkness, "Wrong watermark darkness"
            
        if stamp_location_id:
            logging.info("Check stamp location id Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["locationId"] == stamp_location_id, "Wrong stamp location id"
        
        if stamp_policy:
            logging.info("Check stamp policy Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["policy"] == stamp_policy, "Wrong stamp policy"
            
        if stamp_content:
            logging.info("Check stamp content Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["stampContent"] == stamp_content, "Wrong stamp content"
            
        if stamp_text_color:
            logging.info("Check stamp text color Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["textColor"] == stamp_text_color, "Wrong stamp text color"
        
        if stamp_text_font:
            logging.info("Check stamp text font Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["textFont"] == stamp_text_font, "Wrong stamp text font"
        
        if stamp_text_size:
            logging.info("Check stamp text size Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["textSize"] == stamp_text_size, "Wrong stamp text size"

        if stamp_starting_page:
            logging.info("Check stamp starting page Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["startingPage"] == stamp_starting_page, "Wrong stamp starting page"
        
        if stamp_starting_number:
            logging.info("Check stamp starting number Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["startingNumber"] == stamp_starting_number, "Wrong stamp starting number"
        
        if stamp_num_of_digit:
            logging.info("Check stamp number of digit Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["numberOfDigits"] == stamp_num_of_digit, "Wrong stamp number of digit"
        
        if stamp_page_numbering:
            logging.info("Check stamp page numbering Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["pageNumberingStyle"] == stamp_page_numbering, "Wrong stamp page numbering"
        
        if stamp_white_background:
            logging.info("Check stamp white background Setting")
            assert copy_job_details["pipelineOptions"][stamp_location]["whiteBackground"] == stamp_white_background, "Wrong stamp white background"
        
    @staticmethod
    def get_copy_default_ticket(cdm):
        """Gets the copy default body

        Args:
            cdm: CDM instance

        Returns:
            Default body of copy ticket
        """

        ticket_default_response = cdm.get_raw(cdm.JOB_TICKET_COPY)
        assert ticket_default_response.status_code < 300
        ticket_default_body = ticket_default_response.json()
        return ticket_default_body
    
    @staticmethod
    def patch_operation_on_default_copy_job_ticket(cdm, ticket_default_body):
        response = cdm.patch_raw(cdm.JOB_TICKET_COPY, ticket_default_body)
        assert response.status_code == 200, "PATCH OPERATION WAS UNSUCCESSFUL" + cdm.JOB_TICKET_COPY

    @staticmethod
    def reset_copy_default_ticket(cdm, ticket_body):
        """Sets the default body of copy ticket

        Args:
            cdm: CDM instance
            ticket_body: content to be the default body for default copy ticket

        """
        put_response = cdm.put_raw(cdm.JOB_TICKET_COPY, ticket_body)
        assert put_response.status_code < 300
    
    def build_payload(self, settings):
        """
        Create payload from settings

        Args:
            settings: configuration parameter copy 
        """
        payload = {}

        source = "scan"
        if("src" in settings):
            source = settings["src"]
        payload["src"] = {}
        payload["src"][source] = {}

        if ("color_mode" in settings):
            payload["src"][settings["src"]]["colorMode"] = settings["color_mode"]

        if("resolution" in settings):
            payload["src"][settings["src"]]["resolution"] = settings["resolution"]

        if("output_canvas" in settings):
            payload["pipelineOptions"] = { "imageModifications" : {
                "outputCanvasMediaSize": settings["output_canvas"]["outputCanvasMediaSize"],
                "outputCanvasMediaId": settings["output_canvas"]["outputCanvasMediaId"],
                "outputCanvasCustomWidth": settings["output_canvas"]["outputCanvasCustomWidth"],
                "outputCanvasCustomLength": settings["output_canvas"]["outputCanvasCustomLength"],
                "outputCanvasAnchor": settings["output_canvas"]["outputCanvasAnchor"],
                "outputCanvasOrientation": settings["output_canvas"]["outputCanvasOrientation"]
            }}

        destination = "print"
        if("dest" in settings):
            destination = settings["dest"]
        payload["dest"] = {}
        payload["dest"][destination] = {}

        if("copies" in settings):
            payload["dest"][destination]["copies"] = settings["copies"]

        if("rotate" in settings):
            payload["dest"][destination]["rotate"] = settings["rotate"]

        if("mediaSource" in settings):
            payload["dest"][destination]["mediaSource"] = settings["mediaSource"]

        return payload
    
    def create_run_configuration_copy(self, settings, wait_time=60):
        """
        Create and run configuration copy

        Args:
            settings: configuration parameter copy 
            wait_time: time expected to wait for job finished
        """
        payload = self.build_payload(settings)
        self.do_copy_job(**payload, waitTime=wait_time)

    def dismiss_mdf_eject_page_alert(self):
        """
        This headless method is to dismiss mdfEjectPage alert when perform copy on MDF
        """
        logging.info("Try to dismiss_mdf_eject_page_alert")
        alert_detail = self._cdm.alerts.wait_for_alerts("mdfEjectPage")[0]
        url = alert_detail["actions"]["links"][0]["href"]
        action_value = alert_detail["actions"]["supported"][0]["value"]["seValue"]
        self._cdm.put(url, {"jobAction" : action_value})

    def start_job_on_prepare_processing_no_completion_check(self, job, ticket_id, max_wait_time = 20):
        """Starts a job with prepare processing patch

        Args:
            ticket_id: Ticket ID generated by createJob
            wait_time: Timeout to check the for copy job state
        Returns:
            int: new job id created
        """
        job_id = job.create_job(ticket_id)
        print("|", ctime(), "| ", "Created Job Id:", job_id)
        cancelRequested = False
        # Check for job state created
        job.check_job_state(job_id, "created", max_wait_time)
        # initialize Job
        status_code = job.change_job_state(job_id, 'Initialize', 'initializeProcessing')
        print("|", ctime(), "| ", "Initialized Job Id:", job_id)
        # Check for job state ready
        job.check_job_state(job_id, "ready", max_wait_time)
        status_code = job.change_job_state(job_id, 'Prepare_Processing', 'prepareProcessing')
        print("|", ctime(), "| ", "Started Job with prepare processing, Id:", job_id)
        return job_id

    def copy_simulation_force_start_CDM(self, height, width, settings, job, scan_action):

        """Configures a copy job and performs copy job by CDM

        Args:
            height, width : Size of the scan plot
            settings: copy settings
            job: fixture
            scan_action: intance of dunetuf.scan.ScanAction to perform scan actions

        Returns:
            None
        """
        # Configure scan size and mode
        scan_action.set_scan_random_acquisition_mode(height, width)

        # Create payload
        payload = self.build_payload(settings)
        # Create ticket
        ticket_id = self.get_copy_job_ticket(payload)
        # Create a Job with the ticket
        job_id = self.start_job_on_prepare_processing_no_completion_check(job, ticket_id, 60)
        # Wait for start processing of job
        job.check_job_state(job_id, "processing", 30)

        # The system need sometimes to be ready to start the job 
        # TODO change for a tcl for better wait for state
        time.sleep(20)

        # Patch start processing to indicate final of job
        job.change_job_state(job_id, 'Start', 'startProcessing')

        # Wait completion status and validate is completed
        job.check_job_state(job_id, "completed", 80)

        # Get status job
        job.check_job_completion_status(job_id,"success")

        scan_action.reset_simulation_mode()

    def copy_pnm_simulation_force_start_CDM(self, file_hash, settings, job, ssh, scan_action):
        """
        Configures a copy job and performs copy job by CDM using pnm simulation

        Args:
            file_hash (str): The file id of the PNM file to be copied.
            settings (dict): The copy settings.
            job (object): The fixture object.
            ssh (object): The SSH object for file deletion.
            scan_action (object): An instance of dunetuf.scan.ScanAction to perform scan actions.

        Returns:
            None
        """
        # Configure scan size and mode. Setup scanner to work with pnm and use a pnm file.
        destination_path = scan_action.set_scan_pnm_acquisition_mode_hash_file(file_hash)

        # Create payload
        payload = self.build_payload(settings)
        # Create ticket
        ticket_id = self.get_copy_job_ticket(payload)
        # Create a Job with the ticket
        job_id = self.start_job_on_prepare_processing_no_completion_check(job, ticket_id, 60)
        # Wait for start processing of job
        job.check_job_state(job_id, "processing", 30)

        # The system need sometimes to be ready to start the job 
        # TODO change for a tcl for better wait for state
        time.sleep(20)

        # Patch start processing to indicate final of job
        job.change_job_state(job_id, 'Start', 'startProcessing')

        # Wait completion status and validate is completed
        job.check_job_state(job_id, "completed", 80)

        # Get status job
        job.check_job_completion_status(job_id,"success")

        CommonActions.delete_file_by_ssh(ssh, "/tmp/", destination_path)

        scan_action.reset_simulation_mode()

    def copy_simulation(self, height, width, settings, scan_action):

        """Configures a copy job and performs copy job by CDM

        Args:
            height, width : Size of the scan plot
            settings: copy settings

        Returns:
            None
        """
        # Configure scan size and mode
        scan_action.set_scan_random_acquisition_mode(height, width)

        # Create payload
        payload = self.build_payload(settings)

        self.do_copy_job(**payload, waitTime=90)

    def is_constraints_include_print_margins_in_cdm(self, print_margins = "clipContents"):	
        """Verify if the option is included in print margins by CDM	
        Args:	
            print_margins: print margins for the Copy settings	
            eg: clipContents, addToContents, oversize	
        Returns:	
            bool	
        """	

        all_validators = self._cdm.get(self._cdm.JOB_TICKET_COPY_CONSTRAINTS)["validators"]	
        print_margins_supported = False

        for validator in all_validators:	
            if validator.get("propertyPointer", None) == "dest/print/printMargins":	
                for option in validator["options"]:	
                    if print_margins == option.get("seValue"):	
                        print_margins_supported = True	
                        break	

        if print_margins_supported == False:	
            logging.info("The current machine does not support %s" %print_margins)	
            return print_margins_supported	
        else:	
            logging.info("The current machine support %s" %print_margins)	
            return print_margins_supported

    def wait_for_corresponding_scanner_status_with_cdm(self, expected_scanner_status = "Idle", timeout = 100, raise_exception=True,wait_time=1):
        """
            Wait for corresponding scanner status with cdm
            expected_scanner_status (str, optional): [description]. Defaults to "Idle".
            timeout (int, optional): [description]. Defaults to 100.

        Raises:
            Exception: [description]
        """
        logging.info(f"wait_for_corresponding_scanner_status_with_cdm -> {expected_scanner_status}")
        try:
            state_expected_found = False
            start_time = time.time()
            while(time.time()-start_time < timeout):
                response = self._cdm.get(self._cdm.SCANNER_STATUS)
                logging.info(f"current status is <{response['scannerState']}>")
                if response['scannerState'] == expected_scanner_status:
                    logging.info(f"Expected status: <{expected_scanner_status}> displayed Response: {response}")
                    state_expected_found = True
                    break
                
                # Wait one second before checking again to avoid override udw system
                time.sleep(wait_time)
            
            if raise_exception and not state_expected_found:
                raise Exception(f"Failed to get expected status <{expected_scanner_status}>")
        except Exception as e:
            assert False, f"Failed to get scanner status: <{expected_scanner_status}> with cdm, exception is <{e}>"


    def is_constraints_include_media_destination_in_cdm(self, media_destinations = "standard-bin"):
        """Verify if the option is included in media destination by CDM	
        Args:	
            media_destinations: media destination for the Copy settings	
            eg: standard-bin, tray-1, tray-2 ..	
        Returns:	
            bool	
        """	

        all_validators = self._cdm.get(self._cdm.JOB_TICKET_COPY_CONSTRAINTS)["validators"]	
        media_destinations_supported = False	

        for validator in all_validators:	
            if validator.get("propertyPointer", None) == "dest/print/mediaDestination":	
                for option in validator["options"]:	
                    if media_destinations == option.get("seValue"):	
                        media_destinations_supported = True	
                        break	

        if media_destinations_supported == False:	
            logging.info("The current machine does not support %s" %media_destinations)	
            return media_destinations_supported	
        else:	
            logging.info("The current machine support %s" %media_destinations)	
            return media_destinations_supported            
    
    def is_constraints_include_staple_option_in_cdm(self, staple_options = "none"):	
        """Verify if the option is included in staple option by CDM	
        Args:	
            staple_options: staple option for the Copy settings	
            eg: none, two left, two right ..	
        Returns:	
            bool	
        """	

        all_validators = self._cdm.get(self._cdm.JOB_TICKET_COPY_CONSTRAINTS)["validators"]	
        staple_supported = False	

        for validator in all_validators:	
            if validator.get("propertyPointer", None) == "dest/print/stapleOption":	
                for option in validator["options"]:	
                    if staple_options == option.get("seValue"):	
                        staple_supported = True	
                        break	

        if staple_supported == False:	
            logging.info("The current machine does not support %s" %staple_options)	
            return staple_supported	
        else:	
            logging.info("The current machine support %s" %staple_options)	
            return staple_supported     

    def is_constraints_include_punch_option_in_cdm(self, punch_options = "none"):	
        """Verify if the option is included in punch option by CDM	
        Args:	
            punch_options: punch option for the Copy settings	
            eg: none, leftTwoPointDin, leftThreePointUs, leftFourPointSwd..	
        Returns:	
            bool	
        """	

        all_validators = self._cdm.get(self._cdm.JOB_TICKET_COPY_CONSTRAINTS)["validators"]	
        punch_supported = False

        for validator in all_validators:	
            if validator.get("propertyPointer", None) == "dest/print/punchOption":	
                for option in validator["options"]:	
                    if punch_options == option.get("seValue"):	
                        punch_supported = True	
                        break	

        if punch_supported == False:	
            logging.info("The current machine does not support %s" %punch_options)	
            return punch_supported	
        else:	
            logging.info("The current machine support %s" %punch_options)	
            return punch_supported     

    def set_copymode_indirect( self ):
        """Set copy mode to indirect
        """
        self._cdm.put(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT, {"copyMode": "printAfterScanning"})

    def set_copymode_direct( self ):
        """Set copy mode to direct
        """
        self._cdm.put(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT, {"copyMode": "printWhileScanning"})

    def set_interrupt_enabled(self):
        """Set allow interrupt to true
        """
        self._cdm.put(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT, {"allowInterrupt": "true"})

    def set_interrupt_disabled(self):
        """Set allow interrupt to false
        """
        self._cdm.put(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT, {"allowInterrupt": "false"})

    def reset_copymode_to_default(self, configuration):
        """Reset copy mode to default
        """ 
        # Only GSB (designjet) that are MDF support copy mode, rest of products won't do anything if call to this method
        if configuration.familyname == "designjet":
            self.set_copymode_indirect()

    def is_copymode_supported(self):
        '''
        Check if copy mode is supported
        '''
        response = self._cdm.get(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT)
        return "copyMode" in response and response["copyMode"] != "_undefined_"

    def is_copymode_indirect( self ):
        """Check if copy mode is indirect
        """
        response = self._cdm.get(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT)
        return response["copyMode"] == "printAfterScanning"
    
    def is_copymode_direct( self ):
        """Check if copy mode is direct
        """
        response = self._cdm.get(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT)
        return response["copyMode"] == "printWhileScanning"    
            
    def is_allow_interrupt_active(self):
        """Check if allow interrupt is active
        """
        response = self._cdm.get(CdmEndpoints.COPY_CONFIGURATION_ENDPOINT)
        return response["allowInterrupt"] == "true"

    def configure_copy_image_preview_mode(self, cdm, preview_mode: str = "optional"):
        # Get the default job ticket body and do patch operation to set the preview mode
        copy_ticket_default_body = self.get_copy_default_ticket(cdm)
        default_job_ticket = copy.deepcopy(copy_ticket_default_body)
        copy_ticket_default_body["pipelineOptions"]["manualUserOperations"]["imagePreviewConfiguration"] = preview_mode
        self.patch_operation_on_default_copy_job_ticket(cdm, copy_ticket_default_body)
        return default_job_ticket

    def wait_for_job_state(self, jobid: str, expected_states: List[JobState]) -> str:
        """Wait for the specified job to complete and verify job completion state.

        Args:
            jobid: jobid of the job
            expected_states: list of expected job states

        Returns:
            jobstate: final job state
        """
        return self._job_manager.wait_for_job_state(self._job.get_jobid(jobid), expected_states)

    def wait_for_job_completion(self, jobid: str) -> str:
        """Wait for the specified job to complete and verify job completion state.

        Args:
            jobid: jobid of the job

        Returns:
            jobstate: final job state
        """
        return self._job_manager.wait_for_job_completion(self._job.get_jobid(jobid))

    def delay_job(self, delay: int):
        """Delay the next copy job a specified number of seconds.

        Args:
            delay: delay in seconds before printing

        Returns:
            None
        """
        self._job_manager.delay_job(delay, random=False, resource=ResourceService.PrintDeviceService)
    
    def release_delay(self) -> None:
        """Release the delay of print jobs if were delayed.

        Returns:
            None
        """
        self._job_manager.release_delay_job()
