#!groovy

def tryStep(String message, Closure block, Closure tearDown = null) {
    try {
        block()
    }
    catch (Throwable t) {
        slackSend message: "${env.JOB_NAME}: ${message} failure ${env.BUILD_URL}", channel: '#ci-channel', color: 'danger'
        throw t
    }
    finally {
        if (tearDown) {
            tearDown()
        }
    }
}

node {
    stage("Checkout") {
        checkout scm
    }

    stage('Test') {
        // Get a fresh project name to prevent conflicts between concurrent builds.
        gitHash = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
        project = 'dso_api_' + gitHash
        tryStep "test", {
            sh "docker-compose -p ${project} -f src/.jenkins/test/docker-compose.yml build --pull && " +
               "docker-compose -p ${project} -f src/.jenkins/test/docker-compose.yml run -u root --rm test"
        }, {
            sh "docker-compose -p ${project} -f src/.jenkins/test/docker-compose.yml down"
        }
    }   
    
    // The rebuilding likely reuses the build cache from docker-compose.
    stage("Build API image") {
        tryStep "build", {
            docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                def image = docker.build("datapunt/dataservices/dso-api:${env.BUILD_NUMBER}", "src")
                image.push()
            }
        }
    }

    stage("Build API-Docs image") {
        tryStep "build docs", {
            catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                    def image = docker.build("datapunt/dataservices/dso-api-docs:${env.BUILD_NUMBER}", "--build-arg BUILD_NUMBER=${env.BUILD_NUMBER} docs")
                    image.push()
                }
            }
        }
    }
}


String BRANCH = "${env.BRANCH_NAME}"

if (BRANCH == "master") {

    node {
        stage('Push acceptance image') {
            tryStep "image tagging", {
                docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                    def image = docker.image("datapunt/dataservices/dso-api:${env.BUILD_NUMBER}")
                    image.pull()
                    image.push("acceptance")
                }
            }
            tryStep "docs image tagging", {
                docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                    def image = docker.image("datapunt/dataservices/dso-api-docs:${env.BUILD_NUMBER}")
                    image.pull()
                    image.push("acceptance")
                }
            }
        }
    }

    node {
        stage("Deploy to ACC") {
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'acceptance'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy-dataservices-mdbrole.yml'],
                ]
            }
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'acceptance'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy.yml'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOKPARAMS', value: "-e cmdb_id=app_dso-api"]
                ]
            }
            /*
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'acceptance'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy.yml'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOKPARAMS', value: "-e cmdb_id=app_dso-api-docs"]
                ]
            }
            */
        }
    }
   
    node {
        stage('OWASP vulnerability scan') {
            // Get a fresh project name to prevent conflicts between concurrent builds.
            gitHash = sh(script: 'git rev-parse --short HEAD', returnStdout: true).trim()
            project = 'owasp_check_' + gitHash

            tryStep "owasp vulnerability check", {
                sh  "docker-compose -p ${project} -f src/.jenkins/owasp_vulnerability_scan/docker-compose.yml build --pull && " +
                    "docker-compose -p ${project} -f src/.jenkins/owasp_vulnerability_scan/docker-compose.yml run -u root --rm test"
            }, {
                sh  "docker-compose -p ${project} -f src/.jenkins/owasp_vulnerability_scan/docker-compose.yml down"
            }
        }
    }
        /* stage('OpenAPI specification check') { */
        /*     tryStep "openapi specification check", { */
        /*         sh  "docker-compose -p openapi_validator -f src/.jenkins/openapi_validator/docker-compose.yml build --pull && " + */
        /*             "docker-compose -p openapi_validator -f src/.jenkins/openapi_validator/docker-compose.yml run -u root --rm --entrypoint='' test /var/run_validator.sh" */
        /*     }, { */
        /*         sh  "docker-compose -p openapi_validator -f src/.jenkins/openapi_validator/docker-compose.yml down" */
        /*     } */
        /* } */
   /* } */

    stage('Waiting for approval') {
        slackSend channel: '#ci-channel', color: 'warning', message: 'DSO-API is waiting for Production Release - please confirm'
        input "Deploy to Production?"
    }    

    node {
        stage('Push production image') {
            tryStep "image tagging", {
                docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                    def image = docker.image("datapunt/dataservices/dso-api:${env.BUILD_NUMBER}")
                    image.pull()
                    image.push("production")
                    image.push("latest")
                }
            }
            tryStep "docs image tagging", {
                docker.withRegistry("${DOCKER_REGISTRY_HOST}",'docker_registry_auth') {
                    def image = docker.image("datapunt/dataservices/dso-api-docs:${env.BUILD_NUMBER}")
                    image.pull()
                    image.push("production")
                    image.push("latest")
                }
            }
        }
    }

    node {
        stage("Deploy") {
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'production'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy-dataservices-mdbrole.yml'],
                ]
            }
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'production'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy.yml'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOKPARAMS', value: "-e cmdb_id=app_dso-api"]
                ]
            }
            tryStep "deployment", {
                build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'production'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy.yml'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOKPARAMS', value: "-e cmdb_id=app_dso-api-docs"]
                ]
            }
        }
    }

}
