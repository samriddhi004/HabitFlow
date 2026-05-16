pipeline {
    agent any

    environment {
        IMAGE_NAME     = "habitflow"
        DOCKERHUB_CRED = credentials('dockerhub-credentials')
        IMAGE_FULL     = "${DOCKERHUB_CRED_USR}/${IMAGE_NAME}"
        CONTAINER_NAME = "habitflow-app"
        APP_PORT       = "5000"
    }

    stages {

        // ── 1. Checkout ──────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                echo "✅ Code checked out — build #${BUILD_NUMBER} on branch ${GIT_BRANCH}"
            }
        }

        // ── 2. Build Docker Image ────────────────────────────────────────
        stage('Build') {
            steps {
                dir('app') {
                    sh """
                        docker build \
                          --build-arg APP_VERSION=${BUILD_NUMBER} \
                          -t ${IMAGE_FULL}:${BUILD_NUMBER} \
                          -t ${IMAGE_FULL}:latest \
                          .
                    """
                }
                echo "✅ Image built: ${IMAGE_FULL}:${BUILD_NUMBER}"
            }
        }
        
        // ── 3. Smoke Test ────────────────────────────────────────────────
        stage('Test') {
            steps {
                sh """
                    docker run --rm -d \
                      --name habitflow-test-${BUILD_NUMBER} \
                      --network monitoring \
                      -e APP_VERSION=test \
                      ${IMAGE_FULL}:${BUILD_NUMBER}

                    sleep 6

                    docker run --rm \
                      --network monitoring \
                      curlimages/curl:latest \
                      curl -sf http://habitflow-test-${BUILD_NUMBER}:5000/health \
                      && echo "✅ Health endpoint OK" \
                      || (echo "❌ Health check failed"; docker stop habitflow-test-${BUILD_NUMBER}; exit 1)

                    docker stop habitflow-test-${BUILD_NUMBER}
                """
            }
        }

        // ── 4. Push to Docker Hub ────────────────────────────────────────
        stage('Push') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-credentials',
                    usernameVariable: 'DH_USER',
                    passwordVariable: 'DH_PASS'
                )]) {
                    sh """
                        echo \$DH_PASS | docker login -u \$DH_USER --password-stdin
                        docker push ${IMAGE_FULL}:${BUILD_NUMBER}
                        docker push ${IMAGE_FULL}:latest
                    """
                }
                echo "✅ Pushed ${IMAGE_FULL}:${BUILD_NUMBER}"
            }
        }

        // ── 5. Deploy via Ansible ────────────────────────────────────────
        stage('Deploy') {
            steps {
                sh """
                    ansible-playbook \
                      -i ansible/inventory.ini \
                      ansible/deploy.yml \
                      -e "image_full=${IMAGE_FULL}" \
                      -e "image_tag=${BUILD_NUMBER}" \
                      -e "container_name=${CONTAINER_NAME}" \
                      -e "app_port=${APP_PORT}"
                """
                echo "✅ Deployed via Ansible — version ${BUILD_NUMBER}"
            }
        }

        // ── 6. Post-deploy Health Check ──────────────────────────────────
        stage('Health Check') {
            steps {
                sh """
                    sleep 5
                    curl -sf http://localhost:${APP_PORT}/health \
                      && echo "✅ App is live on port ${APP_PORT}" \
                      || (echo "❌ Post-deploy health check FAILED"; exit 1)
                """
            }
        }

        // ── 7. Cleanup ───────────────────────────────────────────────────
        stage('Cleanup') {
            steps {
                sh "docker image prune -f"
                echo "✅ Stale images pruned"
            }
        }
    }

    post {
        success {
            echo "🚀 HabitFlow v${BUILD_NUMBER} deployed successfully!"
        }
        failure {
            echo "💥 Pipeline FAILED — check stage logs above"
        }
        always {
            sh "docker logout || true"
        }
    }
}
