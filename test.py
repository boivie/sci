import time, itertools, sys
from sci import Job

job = Job(__name__)

build_id_prefix = job.parameter("BUILD_ID_PREFIX", "The build ID prefix to use")
branch = job.parameter("BRANCH", "Manifest branch", required = True)
manifest_file = job.parameter("MANIFEST_FILE", "Manifest Filename",
                              default = "default.xml")
products = job.parameter("PRODUCTS", "Products to build", type = "array")
variants = job.parameter("VARIANTS", "Variants to build", type = "array",
                         default = ["eng", "userdebug", "user"])

build_id = job.env("BUILD_ID")


@job.default(products)
def get_products():
    if "donut" in branch():
        return ["g1", "emulator"]
    if "eclair" in branch():
        return ["droid", "nexus_one", "emulator"]
    if "gingerbread" in branch():
        return ["nexus_one", "nexus_s", "emulator"]
    raise job.error("Don't know which products to build!")


@job.default(build_id_prefix)
def default_build_id_prefix():
    return branch().upper().replace("-", "_")


@job.step("Create Build ID")
def create_build_id():
    build_id.set(build_id_prefix() + "_" + time.strftime("%y%m%d_%H%M%S"))


@job.step("Create Static Manifest")
def create_manifest():
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}} -m {{MANIFEST_FILE}}")
    job.run("repo sync --jobs={{SYNC_JOBS}}", name = "sync")
    job.run("repo manifest -r -o static_manifest.xml")

    job.store("static_manifest.xml")


@job.step("Run single matrix job")
def run_single_matrix_job(product, variant):
    result_file = "result-" + build_id() + "-" + \
        product + "-" + variant + ".zip"
    job.get_stored("static_manifest.xml")
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}}")
    job.run("cp static_manifest.xml .repo/manifest.xml")
    job.run("repo sync --jobs={{SYNC_JOBS}}", name = "sync")
    job.run("""
. build/envsetup.sh
lunch {{product}}-{{variant}}
make -j{{jobs}}""", name = "build",
            args = {"product": product, "variant": variant,
                    "jobs": job.get_var("JOB_CPUS") + 1})
    job.run("zip {{result_file}} $OUT/*.img", name = "zip",
            args = {"result_file": result_file})
    job.store(result_file)


@job.step("Run matrix jobs")
def run_matrix_jobs():
    comb = itertools.product(products(), variants())
    for product, variant in comb:
        run_single_matrix_job.run_detached(product, variant)


@job.step("Send Report")
def send_report():
    pass


@job.main()
def run():
    create_build_id()
    job.set_description(build_id())
    create_manifest()
    run_matrix_jobs()
    send_report()


print(job.info())
job.start(BRANCH = sys.argv[1])
