from testbase import EmptyTestBase


class TC(EmptyTestBase):
    def testDescription(self):
        self.job.description = "Hello"
        assert(self.job.description == "Hello")

        self.job.env["FOO"] = "foo"
        self.job.description = "test-{{FOO}}"
        assert(self.job.description == "test-foo")
