import zipfile, time, os
from tempfile import NamedTemporaryFile
from zipimport import zipimporter
from .session import Session
from .environment import Environment
from .utils import random_sha1

_package_dir = os.path.join(os.path.dirname(__file__), "packages")
if not os.path.exists(_package_dir):
    os.makedirs(_package_dir)


def _find_job(module):
    from .job import Job
    # Find the 'job' variable
    for k in dir(module):
        var = getattr(module, k)
        if issubclass(var.__class__, Job):
            return var
    raise Exception("Couldn't locate the Job variable")


def _find_entrypoint(job, name):
    if not name:
        return job._mainfn
    for step in job.steps:
        if step[1].__name__ == name:
            return step[1]
    raise Exception("Couldn't locate entry point")


def get_package(package_name):
    return os.path.join(_package_dir, package_name)


def run_package(session, location, entrypoint_name = "",
                params = {}, args = [], kwargs = {}, env = None, flags = {}):
    # Hard-link or copy the package to the session directory
    dest_package = os.path.join(session.path, "packaged-job.zip")
    source_package = get_package(location.package)
    os.link(source_package, dest_package)

    zmod = zipimporter(dest_package)
    mod = zmod.load_module(location.filename.replace(".py", ""))

    job = _find_job(mod)
    entrypoint = _find_entrypoint(job, entrypoint_name)

    if env:
        env = Environment.deserialize(env)

    job.location = location
    ret = job._start(session, entrypoint, params, args, kwargs, env, flags)

    # Update the session
    session = Session.load(session.id)
    session.return_value = ret
    session.return_code = 0  # We finished without exceptions.
    session.state = "finished"
    session.save()
    return ret


def should_archive(root, directory):
    if os.path.exists(os.path.join(root, directory, "_do_not_package.txt")):
        return False
    return True


def create_pkg(srcdir):
    rand = random_sha1()[0:7]
    basename = "private-%s-%s.zip" % (time.strftime("%y%m%d_%H%M%S"), rand)
    destfname = os.path.join(_package_dir, basename)
    with NamedTemporaryFile(dir = os.path.dirname(destfname),
                            delete = False) as f:
        zf = zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED)
        for root, dirnames, filenames in os.walk(srcdir):
            dirnames[:] = [d for d in dirnames if should_archive(root, d)]
            for filename in filenames:
                filename = os.path.realpath(os.path.join(root, filename))
                zf.write(filename, os.path.relpath(filename, srcdir))
        zf.close()
        os.rename(f.name, destfname)
        return destfname
    raise Exception("Failde to create package")
