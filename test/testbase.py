import unittest, sys, os
sys.path.append("../")
from sci import Job


class EmptyTestBase(unittest.TestCase):
    def setUp(self):
        if "SCI_MASTER_URL" in os.environ:
            del os.environ["SCI_MASTER_URL"]
        if "SCI_JOB_KEY" in os.environ:
            del os.environ["SCI_JOB_KEY"]
        self.job = Job(__name__)

        @self.job.main()
        def main():
            pass

    pass
