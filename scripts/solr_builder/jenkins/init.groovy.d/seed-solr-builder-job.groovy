// Idempotently create the solr_builder pipeline jobs ("Pipeline script from SCM").
// Runs once at first boot from /usr/share/jenkins/ref/init.groovy.d/.
//
// Two jobs run SIDE BY SIDE on separate data stores:
//   solr-builder       legacy postgres pipeline   (scripts/solr_builder/Jenkinsfile)
//   solr-builder-rust  lake/Rust pipeline         (scripts/solr_builder/Jenkinsfile.rust)
//
// Env knobs (set via compose):
//   SEED_BRANCH  branch both jobs track (bare name or */name spec; default master)
//   SEED_REPO    git URL (default https://github.com/internetarchive/openlibrary.git)
//
// NOTE: this file's name contains dashes, so Groovy cannot compile script METHODS
// here (illegal class name). Keep everything as top-level statements / closures.

import hudson.model.BooleanParameterDefinition
import hudson.model.ParametersDefinitionProperty
import hudson.model.StringParameterDefinition
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.GitSCM
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob

def repoUrl = System.getenv("SEED_REPO") ?: "https://github.com/internetarchive/openlibrary.git"
def requested = System.getenv("SEED_BRANCH")
def branchSpec = (requested != null && !requested.isEmpty()) ?
    (requested.startsWith("*/") ? requested : "*/${requested}") : "*/master"

// ---- Legacy postgres pipeline params (keep in sync with Jenkinsfile) ----
def legacyParams = []
legacyParams << new BooleanParameterDefinition("WIPE_OLD_POSTGRES", false, "If true, removes the current postgres")
legacyParams << new BooleanParameterDefinition("WIPE_OLD_SOLR", false, "If true, removes the current solr")
["INDEX_WORKS", "INDEX_ORPHANS", "INDEX_SUBJECTS", "INDEX_AUTHORS", "INDEX_LISTS"].each { name ->
    def desc = ("If true, reindexes " + name.replace("INDEX_", "").toLowerCase() + " into solr").toString()
    legacyParams << new BooleanParameterDefinition(name, true, desc)
}
legacyParams << new BooleanParameterDefinition("SKIP_IA_METADATA", false, "If true, skips fetching edition metadata from archive.org (testing only; ia_* fields will be empty in solr)")
legacyParams << new StringParameterDefinition("MAX_CORES", "18", "Max number of simultaneous cores")
legacyParams << new StringParameterDefinition("PIP_INDEX_URL", "", "Path to custom PIP index (needed on prod)")
legacyParams << new StringParameterDefinition("HTTPS_PROXY", "", "Proxy for HTTP requests (needed on prod)")
legacyParams << new StringParameterDefinition("NO_PROXY", "archive.org,openlibrary.org,.archive.org,.openlibrary.org", "No proxy for these domains")

// ---- Rust lake pipeline params (keep in sync with Jenkinsfile.rust) ----
def rustParams = []
rustParams << new StringParameterDefinition("DUMP_URL", "https://openlibrary.org/data/ol_dump_latest.txt.gz", "Dump to download (redirects are chased to the dated file)")
rustParams << new StringParameterDefinition("LAKE_HOST_DIR", "/mnt/HC_Volume_106672133/openlibrary/lake_full", "Host dir holding dumps/lake/solr data; bind-mounted 1:1 into the agent")
rustParams << new BooleanParameterDefinition("RESUME", true, "Skip stages whose outputs already exist (chunk files, bronze, etc.)")
rustParams << new BooleanParameterDefinition("WIPE_SOLR", false, "Empty the isolated solr_rust_full data dir before loading")
rustParams << new BooleanParameterDefinition("FETCH_IA_METADATA", true, "Fetch IA lite metadata so ebook_access/has_fulltext are real (~30-90 min). If false, ocaids stay unclassified")
rustParams << new BooleanParameterDefinition("LOAD_SATELLITES", true, "Authors, lists, ratings/reading-log, osp, author aggregates")
rustParams << new BooleanParameterDefinition("SMOKE", false, "Tiny slice (3 chunks, sampled satellites) to prove the wiring end-to-end")
rustParams << new StringParameterDefinition("CHUNK_PARALLELISM", "3", "Parallel gold-chunk transforms")
rustParams << new StringParameterDefinition("POST_CONCURRENCY", "8", "Parallel Solr load streams")
rustParams << new BooleanParameterDefinition("OPTIMIZE", false, "Run optimize=true&maxSegments=1 at the end (hours; optional)")

def jobsSpec = [
    [name: "solr-builder",      jenkinsfile: "scripts/solr_builder/Jenkinsfile",      params: legacyParams],
    [name: "solr-builder-rust", jenkinsfile: "scripts/solr_builder/Jenkinsfile.rust", params: rustParams],
]

if (System.getenv("ADMIN_PASSWORD") in [null, ""]) {
    println("SEEDER: WARNING - ADMIN_PASSWORD is not set; the seeded 'admin' user has an empty password. Restart with ADMIN_PASSWORD=<password> to fix.")
}

def jenkins = Jenkins.get()
jobsSpec.each { spec ->
    WorkflowJob job = jenkins.getItem(spec.name)
    if (job == null) {
        job = jenkins.createProject(WorkflowJob.class, spec.name)
        println("SEEDER: created job '${spec.name}'")
    } else {
        println("SEEDER: job '${spec.name}' already exists")
    }
    // Always refresh SCM + Jenkinsfile so SEED_REPO/SEED_BRANCH retarget existing jobs too.
    def scm = new GitSCM(repoUrl)
    scm.branches = [new BranchSpec(branchSpec)]
    job.definition = new CpsScmFlowDefinition(scm, spec.jenkinsfile)
    def existing = job.getProperty(ParametersDefinitionProperty)
    if (existing != null) {
        job.removeProperty(ParametersDefinitionProperty)
    }
    job.addProperty(new ParametersDefinitionProperty(spec.params))
    job.save()
    def branch = job.definition instanceof CpsScmFlowDefinition ? job.definition.scm.branches[0].name : "n/a"
    println("SEEDER: job '${spec.name}' -> ${spec.params.size()} params; branch ${branch}; file ${spec.jenkinsfile}")
}
