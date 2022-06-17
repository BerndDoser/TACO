#!groovy

pipeline {

  agent {
    label 'docker-host'
  }

  options {
    timeout(time: 1, unit: 'HOURS')
  }

  stages {
    stage('Static Code Checking') {
      steps {
        sh 'find . -name \\*.py | xargs pylint -f parseable | tee pylint.log'
      }
      post {
        always {
          recordIssues(
            tool: pyLint(pattern: 'pylint.log'),
            unstableTotalHigh: 100
          )
        }
      }
    }
    stage('Unit tests') {
      agent {
        dockerfile {
          dir '.devcontainer'
        }
      }
      steps {
        sh 'PYTHONPATH=$WORKSPACE/src pytest --with-xunit --xunit-file=pyunit.xml --cover-xml --cover-xml-file=cov.xml'
      }
      post {
        always {
          recordIssues (
            tool: junitParser(pattern: "pyunit.xml")
          )
        }
      }
    }
  }
  post {
    failure {
      mail to: 'bernd.doser@h-its.org', subject: "FAILURE: ${currentBuild.fullDisplayName}", body: "Failed."
    }
  }
}
