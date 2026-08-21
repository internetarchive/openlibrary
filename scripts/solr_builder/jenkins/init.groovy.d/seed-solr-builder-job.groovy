import hudson.plugins.git.BranchSpec
import hudson.plugins.git.GitSCM
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition
import org.jenkinsci.plugins.workflow.job.WorkflowJob

// Idempotently create the solr_builder pipeline job ("Pipeline script from SCM").
// Runs once at first boot from /usr/share/jenkins/ref/init.groovy.d/.

def jobName = "solr-builder"
def jenkins = Jenkins.get()

if (jenkins.getItem(jobName) != null) {
    println("SEEDER: job '${jobName}' already exists, skipping")
    return
}

def scm = new GitSCM("https://github.com/internetarchive/openlibrary.git")
scm.branches = [new BranchSpec("*/master")]

def definition = new CpsScmFlowDefinition(scm, "scripts/solr_builder/Jenkinsfile")

WorkflowJob job = jenkins.createProject(WorkflowJob.class, jobName)
job.definition = definition
job.save()

println("SEEDER: created job '${jobName}'")
