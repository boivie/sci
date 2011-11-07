import os
from testbase import EmptyTestBase
from sci import Job


class TC(EmptyTestBase):
    def testDefaultSet(self):
        assert "SCI_HOSTNAME" in self.job.env

    def testDateTimeSet(self):
        assert "SCI_DATETIME" in self.job.env

    def testNoMasterURL(self):
        job = Job(__name__)
        assert(job._master_url is None)

    def testMasterURL(self):
        os.environ["SCI_MASTER_URL"] = "http://www.example.net"
        job = Job(__name__)
        assert(job._master_url == "http://www.example.net")

    def testJobKey(self):
        os.environ["SCI_JOB_KEY"] = "abracadabra"
        job = Job(__name__)
        assert(job._job_key == "abracadabra")
