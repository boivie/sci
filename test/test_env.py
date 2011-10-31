from testbase import EmptyTestBase


class TC(EmptyTestBase):
    def testDefaultSet(self):
        assert "SCI_HOSTNAME" in self.job.env

    def testDateTimeSet(self):
        assert "SCI_DATETIME" in self.job.env
