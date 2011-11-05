from testbase import EmptyTestBase
from sci.job import JobException


class TC(EmptyTestBase):
    def testFormatByEnv(self):
        self.job.env["FOO"] = "bar"
        assert(self.job.format("foo-{{FOO}}-fum") == "foo-bar-fum")

    def testFormatByParameter(self):
        self.job.params["FOO"] = "bar"
        assert(self.job.format("foo-{{FOO}}-fum") == "foo-bar-fum")

    def testFormatByConfig(self):
        self.job.config["FOO"] = "bar"
        assert(self.job.format("foo-{{FOO}}-fum") == "foo-bar-fum")

    def testFormatByArgument(self):
        assert(self.job.format("foo-{{FOO}}-fum", FOO = "bar") == "foo-bar-fum")

    def testNoSubstitution(self):
        try:
            self.job.format("foo-{{FOO}}-fum")
            assert(False)
        except JobException:
            pass

    def testPrecedence(self):
        self.job.config["VAR"] = "config"
        assert(self.job.format("{{VAR}}") == "config")
        self.job.env["VAR"] = "env"
        assert(self.job.format("{{VAR}}") == "env")
        self.job.params["VAR"] = "params"
        assert(self.job.format("{{VAR}}") == "params")
        assert(self.job.format("{{VAR}}", VAR = "args") == "args")
