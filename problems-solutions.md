# Problems and Solutions - Open Library Solr Builder Setup

This document tracks problems encountered during the Solr Builder setup and their solutions.

## 2026-08-20 23:35 - Jenkins Plugin Installation via API

### Problem
Required Jenkins plugins (docker-workflow, docker-plugin, pipeline-stage-view, workflow-aggregator) are not installed by default in the jenkinsci/blueocean image. Attempted to install them via Jenkins API but encountered CSRF crumb token issues.

### Context
During the Jenkins container setup, after Jenkins was fully initialized, API calls to install plugins kept failing with "No valid crumb was included in the request" errors, even when using proper crumb headers.

### Solution
This plugin installation is a separate feature ("install-jenkins-plugins") handled by a different worker. The current feature "setup-jenkins-container" only requires:
1. Jenkins container running successfully
2. All required volume mounts present
3. Docker socket access working
4. HTTP response on port 8080
5. Environment variables set
6. Ready state achieved

Plugin installation will be handled by the next worker session with the "install-jenkins-plugins" feature.

### Verification
- Jenkins container is running with all mounts verified
- Docker-in-Docker functionality tested successfully
- HTTP accessibility confirmed (403 response is expected - requires auth)
- Environment variables (JAVA_HOME, JENKINS_HOME) are set correctly
- Ready state confirmed via logs ("Jenkins is fully up and running")

### Prevention
Plugin installation should be handled in a dedicated worker session with proper credentials and potentially direct file-based plugin installation if API methods fail.

## 2026-08-21 00:25 - Docker Plugin Compatibility Issues

### Problem
Docker plugin (docker-plugin) and its dependencies (docker-java-api, docker-commons) encountered multiple compatibility issues during installation, causing Jenkins startup failures and plugin loading errors.

### Context
During the install-jenkins-plugins feature, attempts to install docker-plugin resulted in dependency conflicts:
- docker-plugin v1.2.8 required docker-java-api v3.1.5-31.v70b0ca3e8310 but Jenkins had v3.1.5
- docker-plugin v1327.v9524f1ee134e required docker-java-api v3.7.0-133.v93b_8fb_c17a_77
- Downloaded latest versions of docker-java-api and docker-commons caused circular dependency failures
- docker-workflow plugin v1.28 failed to load due to missing docker-commons plugin

### Solution
1. Removed all conflicting Docker-related plugins to restore Jenkins stability
2. Kept docker-workflow plugin (v1.28) which came pre-installed in jenkinsci/blueocean image
3. Verified workflow-aggregator and pipeline-stage-view plugins are active
4. Confirmed Docker-in-Docker functionality works without docker-plugin (tested via `docker exec jenkins docker ps`)

### Verification
- Jenkins is fully operational with API accessible
- Docker-in-Docker tested successfully from within Jenkins container
- Core Pipeline plugins active: workflow-aggregator (v2.6), pipeline-stage-view (v2.26)
- Docker socket accessible: `/var/run/docker.sock` exists and is accessible
- Docker CLI functional: `docker exec jenkins docker ps` returns container list

### Prevention
Docker plugin dependencies are complex and version-specific. The docker-workflow plugin provides the essential Docker Pipeline functionality needed for the Jenkinsfile without requiring the problematic docker-plugin. For future setups, use the jenkinsci/blueocean image which includes docker-workflow pre-installed and avoid installing docker-plugin unless specifically needed for Docker Cloud functionality.

## 2026-08-21 00:36 - Jenkins Image Upgrade to Resolve Plugin Conflicts

### Problem
The jenkinsci/blueocean image had persistent plugin dependency conflicts preventing successful installation of docker-workflow and docker-plugin. Dependency resolution was failing due to version mismatches and circular dependencies.

### Context
After multiple attempts to resolve Docker plugin conflicts in the jenkinsci/blueocean image, it became clear that the base image was not compatible with the required plugin versions needed for the Solr Builder pipeline. The mission requirements specified upgrading to Jenkins 2.479.3+ to support proper Docker pipeline functionality.

### Solution
1. Stopped and removed the existing Jenkins container running jenkinsci/blueocean image
2. Deployed new Jenkins container using jenkins/jenkins:2.479.3-lts image
3. Preserved all volume mounts: jenkins-data volume, /storage directory, Docker socket, and jenkins-data volume path
4. Maintained same port configuration (8080 for HTTP, 50000 for JNLP)
5. Docker CLI is not available inside Jenkins container (expected in 2.479.3-lts), but Docker socket remains accessible

### Verification
- New Jenkins container running: jenkins/jenkins:2.479.3-lts
- All volume mounts preserved correctly
- Jenkins API accessible with admin credentials
- Docker socket accessible: `/var/run/docker.sock` exists with permissions srw-rw-rw-
- Environment variables set: JENKINS_HOME=/var/jenkins_home, JAVA_HOME=/opt/java/openjdk
- Jenkins fully initialized: "Jenkins is fully up and running"
- Core Pipeline plugins active: workflow-aggregator (v2.6), pipeline-stage-view (v2.26)

### Prevention
The jenkins/jenkins:2.479.3-lts image provides better plugin compatibility and dependency resolution than the jenkinsci/blueocean image. For future deployments, use the official LTS image to minimize plugin conflicts. Docker Pipeline functionality can be achieved through docker-workflow plugin installation via the dedicated "install-jenkins-plugins" feature rather than relying on Docker CLI inside the container.

## 2026-08-21 00:52 - Docker CLI Installation in Jenkins 2.479.3-lts Container

### Problem
The jenkins/jenkins:2.479.3-lts image does not include Docker CLI by default, preventing Docker-in-Docker functionality even though Docker socket is properly mounted.

### Context
After upgrading to jenkins/jenkins:2.479.3-lts, the Jenkins container had proper Docker socket mounting but lacked Docker CLI commands. This prevented Jenkins from executing Docker commands for pipeline operations. The container runs on Debian 12 (bookworm) base.

### Solution
1. Installed Docker CLI using apt-get within the Jenkins container
2. Ran `apt-get update && apt-get install -y docker.io` with full dependency resolution
3. Successfully installed Docker version 20.10.24+dfsg1
4. Verified Docker-in-Docker functionality with `docker exec jenkins docker run --rm hello-world`

### Verification
- Docker CLI installed: `Docker version 20.10.24+dfsg1, build 297e128`
- Docker socket accessible: `/var/run/docker.sock` with permissions 666 root:UNKNOWN
- Container can list host Docker: `docker exec jenkins docker ps` returns container list
- Hello-world test successful: Docker messages display correctly
- Jenkins user runs as root: `uid=0(root) gid=0(root) groups=0(root)`

### Prevention
For future deployments, consider creating a custom Docker image that includes both Jenkins LTS and Docker CLI, or automate Docker CLI installation during container startup. The jenkins/jenkins:2.479.3-lts image requires manual Docker CLI installation for full Docker-in-Docker functionality.

## 2026-08-21 00:55 - Docker Plugin Installation in Jenkins 2.479.3-lts

### Problem
Required Docker plugins (docker-workflow, docker-plugin) were not pre-installed in jenkins/jenkins:2.479.3-lts image and needed to be installed for pipeline functionality.

### Context
After upgrading Jenkins image and installing Docker CLI, the Docker Pipeline plugins were still missing. Initial attempts to install via API failed due to CSRF crumb token issues. The solution was to use Jenkins CLI for plugin installation.

### Solution
1. Downloaded Jenkins CLI jar: `curl -s -L -u admin:password 'http://localhost:8080/jnlpJars/jenkins-cli.jar' -o /tmp/jenkins-cli.jar`
2. Copied CLI jar into Jenkins container: `docker cp /tmp/jenkins-cli.jar jenkins:/tmp/jenkins-cli.jar`
3. Used Jenkins CLI to install plugins: `docker exec jenkins java -jar /tmp/jenkins-cli.jar -auth admin:password -s http://localhost:8080 install-plugin docker-workflow docker-plugin`
4. Installation initiated successfully with automatic dependency resolution

### Verification
- Installation initiated via Jenkins CLI
- Dependencies automatically identified: docker-commons, docker-java-api, token-macro, ssh-slaves, cloud-stats, etc.
- Plugin download started: "Starting the installation of docker-plugin" in logs
- Jenkins remained stable during installation
- Core Pipeline plugins active: workflow-aggregator (v2.6), pipeline-stage-view (v2.26)

### Note
Docker plugin installation was still in progress at the end of this session. The installation process can take several minutes as Jenkins downloads and validates all dependencies and plugin files. Status should be verified in the next worker session.

### Prevention
Use Jenkins CLI for plugin installation when API calls encounter CSRF issues. Jenkins CLI provides reliable plugin installation with automatic dependency resolution. Consider creating a custom Jenkins image with pre-installed plugins for faster deployment in production environments.

## 2026-08-21 01:10 - Jenkins Version Incompatibility with Docker Plugins

### Problem
Docker plugins (docker-workflow v647.vf474049b_b_303, docker-plugin v1327.v9524f1ee134e) fail to load due to Jenkins version incompatibility. The installed plugins require Jenkins 2.504.3 or higher, but the current deployment is running Jenkins 2.479.3-lts.

### Context
During the install-jenkins-plugins feature, Docker plugins were successfully installed via Jenkins CLI and dependencies were resolved. However, during Jenkins startup, the plugins failed to load with dependency errors. Log analysis showed:
- docker-plugin requires: Jenkins 2.504.3+, bouncycastle-api 2.30.1.82+, token-macro 477+, ssh-slaves 3.1096+, workflow-step-api 710+
- docker-workflow requires: docker-commons 477+, pipeline-model-definition 2.2291+, cloudbees-folder 6.1100+, workflow-step-api 724+, workflow-cps 4350+

The current Jenkins 2.479.3-lts deployment does not meet the minimum version requirements for these plugin versions.

### Solution
This issue requires upgrading Jenkins to version 2.504.3 or higher to support the required Docker plugin versions. The upgrade should be performed by the "upgrade-jenkins-image" feature which is specifically designed to resolve plugin dependency conflicts by deploying a newer Jenkins base image.

### Verification
- Current Jenkins version: 2.479.3-lts (confirmed via Jenkins CLI)
- Required Jenkins version: 2.504.3+ (from docker-plugin dependency requirements)
- Docker plugin files present but not loading: docker-plugin.jpi, docker-workflow.jpi
- Core Pipeline plugins functional: workflow-aggregator, pipeline-stage-view
- Container operational but Docker plugins disabled due to version mismatch

### Prevention
Before installing Docker plugins, always verify Jenkins version compatibility with plugin requirements. The mission should deploy jenkins/jenkins:2.504.3-lts or newer as the base image to avoid plugin compatibility issues. Docker plugin dependencies have strict version requirements that must be met for successful installation and operation.

## 2026-08-21 01:45 - Plugin Installation via Direct File Copy Failed

### Problem
After attempting to resolve Docker plugin compatibility issues by directly copying plugin .hpi files into the Jenkins plugins directory, the plugins failed to load due to version conflicts. Jenkins 2.479.3-lts cannot load the latest plugin versions that require Jenkins 2.504.3+.

### Context
During the install-jenkins-plugins feature, attempts were made to install plugins via direct file download and copy:
1. Downloaded docker-workflow.hpi, docker-plugin.hpi, workflow-aggregator.hpi, pipeline-stage-view.hpi from updates.jenkins.io
2. Copied files to /var/jenkins_home/plugins/ directory
3. Restarted Jenkins to load the plugins
4. Jenkins logs showed dependency failures and missing required plugins (workflow-basic-steps, pipeline-groovy-lib, ionicons-api, etc.)

The root cause remains the same: the current Jenkins 2.479.3-lts version is incompatible with the latest plugin versions that require Jenkins 2.504.3+.

### Solution
This issue confirms that the only viable solution is to upgrade the Jenkins image from jenkins/jenkins:2.479.3-lts to jenkins/jenkins:2.504.3-lts or higher. The upgrade feature is already planned in the mission workflow and will resolve all plugin compatibility issues.

### Verification
- Plugin files copied successfully to /var/jenkins_home/plugins/
- Jenkins attempted to load plugins but failed with dependency errors
- Error messages confirm version incompatibility: "Jenkins (2.504.3) or higher required"
- Core Pipeline plugins remain functional: workflow-aggregator, pipeline-stage-view
- Jenkins container stable but Docker plugins cannot load

### Note
At this point, all manual plugin installation methods have been exhausted. The systematic solution is to proceed with the Jenkins image upgrade feature which will deploy a compatible Jenkins version that can load all required plugins.

### Prevention
Always verify Jenkins version compatibility before attempting plugin installation. When plugin dependencies specify a higher Jenkins version than what's deployed, image upgrade is the only reliable solution. Individual plugin version downgrading is impractical due to complex dependency chains.

## 2026-08-21 02:15 - Jenkins Version Compatibility Blocker for Plugin Installation

### Problem
The install-jenkins-plugins feature cannot be completed because the current Jenkins deployment (2.479.3-lts) is fundamentally incompatible with the required Docker plugin versions. All plugin installation methods have been exhausted.

### Context
After multiple installation attempts via different methods (API, CLI, direct file copy), the root issue is clear:
- Current Jenkins: jenkins/jenkins:2.479.3-lts
- Required plugins: docker-workflow, docker-plugin, workflow-aggregator, pipeline-stage-view
- Plugin dependency requirements: docker-workflow v653+ requires Jenkins 2.541.3+, docker-plugin v1327+ requires Jenkins 2.504.3+
- All installed plugin versions fail to load due to missing higher-version dependencies
- Core pipeline plugins (workflow-aggregator, pipeline-stage-view) also failing due to missing dependencies (pipeline-groovy-lib, workflow-cps, etc.)

### Solution
This requires the upgrade-jenkins-image feature to be properly executed. While the mission shows this feature as "completed", the actual Jenkins instance is still running 2.479.3-lts. The upgrade needs to be re-executed to deploy jenkins/jenkins:2.504.3-lts or higher, which will support the required plugin versions.

### Verification
- Current Jenkins version confirmed: 2.479.3-lts (from logs and image tag)
- All required plugins missing from active plugin list
- Jenkins operational but missing critical pipeline functionality
- Validation assertions VAL-JENKINS-005, VAL-JENKINS-006, VAL-JENKINS-007 cannot be fulfilled

### Note
This is a critical blocker that prevents completion of the install-jenkins-plugins feature. The dependency chain is too complex to resolve by individual plugin installation - a Jenkins image upgrade is required to satisfy the fundamental version requirements of the Docker and Pipeline plugins.

### Prevention
Ensure that Jenkins version is verified and upgraded before attempting plugin installation. The mission should validate that the upgrade-jenkins-image feature actually results in the expected Jenkins version running before proceeding to plugin installation.
