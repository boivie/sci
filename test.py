import time, itertools
from sci import Job

job = Job(__name__, debug = True)

# Parameters - to allow a GUI to easily list them
branch          = job.parameter("BRANCH", "Manifest branch", required = True)
build_id_prefix = job.parameter("BUILD_ID_PREFIX", "The build ID prefix to use")
manifest_file   = job.parameter("MANIFEST_FILE", "Manifest Filename",
                                default = "default.xml")
products        = job.parameter("PRODUCTS", "Products to build", type = "array")
variants        = job.parameter("VARIANTS", "Variants to build", type = "array",
                                default = ["eng", "userdebug", "user"])


# This job works as follows    <-- run single matrix job *3 -->
#                           / get source -> build android -> zip \
#  create   ->  create  -> -  get source -> build android -> zip  -  create
# build id     manifest     \ get source -> build android -> zip /   report
#                          <<--------- run matrix jobs ---------->>


@job.default(products)
def get_products():
    """A function that will be evaluated to get the default
       value for 'products' in case it's not specified"""

    if "donut" in branch():
        return ["g1", "emulator"]
    if "eclair" in branch():
        return ["droid", "nexus_one", "emulator"]
    if "gingerbread" in branch():
        return ["nexus_one", "nexus_s", "emulator"]
    job.error("Don't know which products to build!")


@job.default(build_id_prefix)
def default_build_id_prefix():
    return branch().upper().replace("-", "_")


@job.step("Create Build ID")
def create_build_id():
    """A very simple step"""
    build_id = build_id_prefix() + "_" + time.strftime("%y%m%d_%H%M%S")
    return build_id


@job.step("Create Static Manifest")
def create_manifest():
    """These commands will automatically run in a temporary directory
       that will be wiped once the entire job finishes"""
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}} -m {{MANIFEST_FILE}}")
    job.run("repo sync --jobs={{SYNC_JOBS}}", name = "sync")
    job.run("repo manifest -r -o static_manifest.xml")

    # Upload the result of this step to the 'file storage node'
    job.artifacts.add("static_manifest.xml")


@job.step("Get source code")
def get_source():
    job.run("repo init -u {{MANIFEST_URL}} -b {{BRANCH}}")
    job.run("cp static_manifest.xml .repo/manifest.xml")
    job.run("repo sync --jobs={{SYNC_JOBS}}")


@job.step("Build Android")
def build_android():
    job.run("""
. build/envsetup.sh
lunch {{PRODUCT}}-{{VARIANT}}
make -j{{JOBS}}""",
            JOBS = job.get_var("JOB_CPUS") + 1)


@job.step("ZIP resulted files")
def zip_result():
    zip_file = "result-{{BUILD_ID}}-{{PRODUCT}}-{{VARIANT}}.zip"
    input_files = "out/target/product/{{PRODUCT}}/*.img"

    job.artifacts.create_zip(zip_file, input_files)
    return job.format(zip_file)


@job.step("Run single matrix job")
def run_single_matrix_job(product, variant):
    """This job will be running on a separate machine, in parallel with
       a lot of other similar jobs. It will perform a few build steps."""
    job.env["PRODUCT"] = product
    job.env["VARIANT"] = variant
    job.artifacts.get("static_manifest.xml")

    get_source()
    build_android()
    return zip_result()


@job.step("Run matrix jobs")
def run_matrix_jobs():
    """The async function runs the step asynchronously on (possibly)
       another node. This step will wait for all the detached jobs to
       finish before it returns."""
    comb = itertools.product(products(), variants())
    jobs = []
    for product, variant in comb:
        job = run_single_matrix_job.async(product, variant)
        jobs.append(job)

    for job in jobs:
        print("Result: " + job.get())


@job.step("Send Report")
def send_report():
    pass


@job.main()
def main():
    """This is the job's entry point."""
    job.env["BUILD_ID"] = create_build_id()
    job.description = "{{BUILD_ID}}"
    create_manifest()
    run_matrix_jobs()
    send_report()


if __name__ == "__main__":
    job.start()
