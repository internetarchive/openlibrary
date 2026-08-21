import hudson.model.BooleanParameterDefinition
import hudson.model.ParametersDefinitionProperty
import hudson.model.StringParameterDefinition
import hudson.plugins.git.BranchSpec
import hudson.plugins.git.GitSCM
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob

// Idempotently create the solr_builder pipeline job ("Pipeline script from SCM").
// Runs once at first boot from /usr/share/jenkins/ref/init.groovy.d/.
//
// SEED_BRANCH env var selects which branch to track (bare name or */name spec);
// defaults to master. Set via compose: SEED_BRANCH=<branch> docker compose up.

def repoUrl = "https://github.com/internetarchive/openlibrary.git"
def requested = System.getenv("SEED_BRANCH")
def branchSpec = (requested != null && !requested.isEmpty()) ?
    (requested.startsWith("*/") ? requested : "*/${requested}") : "*/master"

// Keep in sync with the parameters block in scripts/solr_builder/Jenkinsfile.
// Defining these at seed time makes them visible in the UI immediately;
// Jenkins re-syncs them from the Jenkinsfile after the first build anyway.
def paramDefs = []
["WIPE_OLD_POSTGRES", "WIPE_OLD_SOLR"].each { name ->
    paramDefs << new BooleanParameterDefinition(name, false, "If true, removes the current ${name.contains('POSTGRES') ? 'postgres' : 'solr'}")
}
["INDEX_WORKS", "INDEX_ORPHANS", "INDEX_SUBJECTS", "INDEX_AUTHORS", "INDEX_LISTS"].each { name ->
    paramDefs << new BooleanParameterDefinition(name, true, "If true, reindexes ${name.replace('INDEX_', '').toLowerCase()} into solr")
}
paramDefs << new BooleanParameterDefinition("SKIP_IA_METADATA", false, "If true, skips fetching edition metadata from archive.org (testing only; ia_* fields will be empty in solr)")
paramDefs << new StringParameterDefinition("MAX_CORES", "18", "Max number of simultaneous cores")
paramDefs << new StringParameterDefinition("PIP_INDEX_URL", "", "Path to custom PIP index (needed on prod)")
paramDefs << new StringParameterDefinition("HTTPS_PROXY", "", "Proxy for HTTP requests (needed on prod)")
paramDefs << new StringParameterDefinition("NO_PROXY", "archive.org,openlibrary.org,.archive.org,.openlibrary.org", "No proxy for these domains")

def jenkins = Jenkins.get()
def jobName = "solr-builder"
WorkflowJob job = jenkins.getItem(jobName)

if (job == null) {
    def scm = new GitSCM(repoUrl)
    scm.branches = [new BranchSpec(branchSpec)]
    def definition = new CpsScmFlowDefinition(scm, "scripts/solr_builder/Jenkinsfile")

    job = jenkins.createProject(WorkflowJob.class, jobName)
    job.definition = definition
    println("SEEDER: created job '${jobName}' tracking ${branchSpec}")
} else {
    // Existing job: keep its SCM/definition, but still refresh params below.
    println("SEEDER: job '${jobName}' already exists")
}

def existing = job.getProperty(ParametersDefinitionProperty)
if (existing != null) {
    job.removeProperty(ParametersDefinitionProperty)
}
job.addProperty(new ParametersDefinitionProperty(paramDefs))
job.save()

println("SEEDER: job '${jobName}' has ${paramDefs.size()} parameters; branch spec: " +
    (job.definition instanceof CpsScmFlowDefinition ? job.definition.scm.branches[0].name : "n/a"))
