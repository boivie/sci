import unittest, sys
sys.path.append("../")
from sci import Job


class EmptyTestBase(unittest.TestCase):
    def setUp(self):
        self.job = Job(__name__)

        @self.job.main()
        def main():
            pass

    pass
