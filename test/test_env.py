from testbase import EmptyTestBase


class TC(EmptyTestBase):
    def testDefaultSet(self):
        self.job.set_default_env()
        assert "SCI_HOSTNAME" in self.job.env
