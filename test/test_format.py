from testbase import EmptyTestBase
from sci.job import JobException


class TC(EmptyTestBase):
    def testFormatByEnv(self):
        self.job.env["FOO"] = "bar"
        print(self.job.env.keys())
        assert(self.job.format("foo-{{FOO}}-fum") == "foo-bar-fum")

    def testFormatByArgument(self):
        assert(self.job.format("foo-{{FOO}}-fum", FOO = "bar") == "foo-bar-fum")

    def testNoSubstitution(self):
        try:
            self.job.format("foo-{{FOO}}-fum")
            assert(False)
        except JobException:
            pass
