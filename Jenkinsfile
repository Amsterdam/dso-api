#!groovy

String API_CONTAINER = "repo.data.amsterdam.nl/datapunt/dataservices/dso-api:${env.BUILD_NUMBER}"

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
        tryStep "test", {
            sh "docker-compose -p dso_api -f src/.jenkins/test/docker-compose.yml build --pull && " +
               "docker-compose -p dso_api -f src/.jenkins/test/docker-compose.yml run -u root --rm test"
        }, {
            sh "docker-compose -p dso_api -f src/.jenkins/test/docker-compose.yml down"
        }
    }

    // The rebuilding likely reuses the build cache from docker-compose.
    stage("Build API image") {
        tryStep "build", {
            def image = docker.build(API_CONTAINER, "--pull ./src")
            image.push()
        }
    }

    stage('Push API acceptance image') {
        tryStep "image tagging", {
            def image = docker.image(API_CONTAINER)
            image.pull()
            image.push("acceptance")
        }
    }

    stage("Deploy to ACC") {
        tryStep "deployment", {
            build job: 'Subtask_Openstack_Playbook',
                parameters: [
                    [$class: 'StringParameterValue', name: 'INVENTORY', value: 'acceptance'],
                    [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy-dso-api.yml'],
                ]
        }
    }

    stage('Waiting for approval') {
        slackSend channel: '#ci-channel', color: 'warning', message: 'DSO-API is waiting for Production Release - please confirm'
        input "Deploy to Production?"
    }

    stage('Push production images') {
        tryStep "Tag public api image", {
            def image = docker.image(API_CONTAINER)
            image.pull()
            image.push("production")
            image.push("latest")
        }
    }

    stage("Deploy") {
        tryStep "deployment", {
            build job: 'Subtask_Openstack_Playbook',
            parameters: [
                [$class: 'StringParameterValue', name: 'INVENTORY', value: 'production'],
                [$class: 'StringParameterValue', name: 'PLAYBOOK', value: 'deploy-dso-api.yml'],
            ]
        }
    }

}
