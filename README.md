# HabitFlow

A minimal habit tracker built as a DevOps demo project.

## Stack
- **App** — Flask + SQLite + APScheduler (smart nudges)
- **CI/CD** — GitHub → Jenkins (7-stage pipeline) → Docker Hub
- **Deploy** — Ansible
- **Monitoring** — Prometheus + Grafana

## Pipeline Flow
git push → Jenkins → Build → Test → Push to DockerHub → Ansible Deploy → Health Check

## Services
| Service | URL |
|---|---|
| App | http://localhost:5000 |
| Jenkins | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

## Quick Start
```bash
docker-compose up -d        # start Jenkins + monitoring
# configure Jenkins (see setup guide)
git push origin master      # triggers pipeline automatically
```

## Monitoring
Prometheus scrapes `/metrics` every 15s. Grafana dashboard auto-loads showing check-ins, nudges fired, broken streaks, CPU and RAM.