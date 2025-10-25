# brandme-infra

**Copyright (c) Brand.Me, Inc. All rights reserved.**

Infrastructure as Code for Brand.Me platform: Terraform and Helm configurations.

## Overview

This repository provisions and deploys all Brand.Me services to Google Kubernetes Engine (GKE) on Google Cloud Platform (GCP).

## Structure

```
brandme-infra/
├── terraform/
│   ├── modules/
│   │   ├── gke/           # GKE cluster configuration
│   │   ├── cloudsql/      # Cloud SQL (PostgreSQL)
│   │   ├── gcs/           # Google Cloud Storage
│   │   ├── vpc/           # VPC and networking
│   │   └── monitoring/    # Observability stack
│   └── environments/
│       ├── dev/
│       ├── staging/
│       └── prod/
└── helm/
    ├── charts/
    │   ├── brandme-gateway/
    │   ├── brandme-core/
    │   ├── brandme-agents/
    │   ├── brandme-chain/
    │   └── brandme-console/
    ├── brandme-umbrella/   # Umbrella chart
    └── values/
        ├── values-dev.yaml
        ├── values-staging.yaml
        └── values-prod.yaml
```

## Terraform

### GCP Resources

- **GKE Cluster**: Managed Kubernetes in `us-east1`
- **Cloud SQL**: PostgreSQL 15 instance
- **GCS Bucket**: Object storage for garment passport blobs
- **VPC**: Network isolation with firewall rules
- **Workload Identity**: Service account management
- **Cloud NAT**: Outbound internet access

### Usage

```bash
cd terraform/environments/dev

# Initialize
terraform init

# Plan
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# Destroy (careful!)
terraform destroy
```

### Outputs

- `gke_cluster_name`: GKE cluster name
- `gke_cluster_endpoint`: Kubernetes API endpoint
- `cloudsql_connection_name`: Cloud SQL connection string
- `gcs_bucket_name`: GCS bucket name

## Helm

### Umbrella Chart

Deploys all Brand.Me services with a single command:

```bash
cd helm

# Install/upgrade
helm upgrade --install brandme ./brandme-umbrella \
  --values values/values-dev.yaml \
  --namespace brandme \
  --create-namespace

# Uninstall
helm uninstall brandme --namespace brandme
```

### Individual Charts

```bash
# Deploy specific service
helm upgrade --install gateway ./charts/brandme-gateway \
  --namespace brandme \
  --create-namespace
```

## Observability Stack

### Prometheus + Grafana

```bash
# Install kube-prometheus-stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### Loki

```bash
# Install Loki
helm repo add grafana https://grafana.github.io/helm-charts
helm install loki grafana/loki-stack \
  --namespace monitoring
```

### OpenTelemetry Collector

```bash
# Install OpenTelemetry Collector
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm install otel-collector open-telemetry/opentelemetry-collector \
  --namespace monitoring
```

## NATS JetStream

```bash
# Install NATS with JetStream
helm repo add nats https://nats-io.github.io/k8s/helm/charts/
helm install nats nats/nats \
  --namespace nats \
  --create-namespace \
  --set nats.jetstream.enabled=true
```

## Secrets Management

### Kubernetes Secrets

```bash
# Create OAuth secrets
kubectl create secret generic oauth-secrets \
  --from-literal=client-id=YOUR_CLIENT_ID \
  --from-literal=client-secret=YOUR_CLIENT_SECRET \
  --namespace brandme

# Create JWT secret
kubectl create secret generic jwt-secret \
  --from-literal=secret=YOUR_JWT_SECRET \
  --namespace brandme

# Create wallet secrets (NEVER commit these!)
kubectl create secret generic wallet-secrets \
  --from-file=cardano-key=./cardano-wallet.key \
  --from-file=midnight-key=./midnight-wallet.key \
  --namespace brandme
```

## CI/CD

GitHub Actions workflows automatically:
1. Build Docker images for all services
2. Push to Google Container Registry (GCR)
3. Run tests and security scans
4. Deploy to GKE on tagged releases

See `/.github/workflows/` for pipeline definitions.

## Deployment Regions

- **Primary**: `us-east1` (US East - South Carolina)
- **Future**: Multi-region support (EU, APAC)

## Scaling

### Horizontal Pod Autoscaler (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: brandme-gateway
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: brandme-gateway
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Vertical Pod Autoscaler (VPA)

Automatically adjusts CPU and memory requests based on usage.

## Disaster Recovery

### Database Backups

Cloud SQL automated backups:
- Daily backups retained for 30 days
- Point-in-time recovery enabled
- Cross-region replication for HA

### Application Data

GCS bucket versioning enabled for all objects.

## Security

- **Network Policies**: Restrict pod-to-pod communication
- **Pod Security Standards**: Enforce restricted PSS
- **RBAC**: Least-privilege access control
- **Workload Identity**: No service account keys in pods
- **Secret Encryption**: Secrets encrypted at rest and in transit

## Monitoring & Alerts

### Key Metrics

- Request rate and latency
- Error rate (4xx, 5xx)
- Database connection pool usage
- NATS message queue depth
- Pod CPU and memory usage

### Alerts

- High error rate (> 5%)
- High latency (p95 > 1s)
- Pod crashes
- Database connection failures
- Disk space warnings

## Cost Optimization

- **Preemptible nodes**: For non-critical workloads
- **Cluster autoscaling**: Scale down during low traffic
- **Resource quotas**: Prevent runaway costs
- **GCS lifecycle policies**: Archive old data to Coldline

## License

Copyright (c) Brand.Me, Inc. All rights reserved.
