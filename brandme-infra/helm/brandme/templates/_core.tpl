{{/*
Copyright (c) Brand.Me, Inc. All rights reserved.
Deployment for a process from the core image (brandme-core/Dockerfile
`runtime` stage: python, uid 10001, no default process).

dict:
  root      the chart context ($)
  component resource suffix (read-api, exports-worker, ...)
  cfg       the component's values
  command   explicit command list (manifests never rely on the image CMD)
  env       extra env YAML (string, already rendered)
  http      true when the process listens on cfg.port with GET /health
  grace     terminationGracePeriodSeconds
  ksa       optional ServiceAccount suffix when it differs from component
            (templates/serviceaccounts.yaml renders it)
*/}}
{{- define "brandme.coreDeployment" -}}
{{- $root := .root -}}
{{- $c := .cfg -}}
{{- $name := include "brandme.componentName" (list $root .component) -}}
{{- $ksa := include "brandme.componentName" (list $root (default .component .ksa)) -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $name }}
  labels:
    {{- include "brandme.labels" (list $root .component) | nindent 4 }}
spec:
  replicas: {{ $c.replicas }}
  revisionHistoryLimit: 5
  {{- if not .http }}
  # No HTTP endpoint: a worker that fails its startup checks exits 2 within
  # seconds, so it must stay up this long to count as available.
  minReadySeconds: 30
  {{- end }}
  selector:
    matchLabels:
      {{- include "brandme.selectorLabels" (list $root .component) | nindent 6 }}
  strategy:
    type: RollingUpdate
    rollingUpdate: {maxSurge: 1, maxUnavailable: 0}
  template:
    metadata:
      labels:
        {{- include "brandme.labels" (list $root .component) | nindent 8 }}
      {{- with $root.Values.podDefaults.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      serviceAccountName: {{ $ksa }}
      {{- include "brandme.podDefaults" $root | nindent 6 }}
      terminationGracePeriodSeconds: {{ .grace }}
      securityContext:
        {{- include "brandme.podSecurityContext" (list $root 10001) | nindent 8 }}
      containers:
        - name: {{ .component }}
          image: {{ include "brandme.image" (list $root "core") | quote }}
          imagePullPolicy: {{ $root.Values.images.pullPolicy }}
          command: {{ toJson .command }}
          {{- if .http }}
          ports:
            - name: http
              containerPort: {{ $c.port }}
              protocol: TCP
          {{- end }}
          env:
            {{- include "brandme.modeEnv" $root | nindent 12 }}
            {{- include "brandme.spannerEnv" $root | nindent 12 }}
            {{- .env | nindent 12 }}
          {{- if .http }}
          # GET /health opens a Spanner snapshot (read_api/reads.py:95-97,
          # privacy_exports/app.py:44-47): readiness tracks the database;
          # liveness is a TCP check so a Spanner outage does not restart pods.
          # The consumer-domain service's /health is static
          # (domains/persona/app.py:79-82): its readiness tracks the process only.
          startupProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 5
            timeoutSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet: {path: /health, port: http}
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          livenessProbe:
            tcpSocket: {port: http}
            periodSeconds: 20
            timeoutSeconds: 3
            failureThreshold: 3
          {{- include "brandme.preStop" $root | nindent 10 }}
          {{- else }}
          # No liveness/readiness probe: the process has no endpoint. It runs
          # its own schema/config/provider checks before working and exits
          # non-zero on failure; Kubernetes restarts it on exit.
          {{- end }}
          resources:
            {{- toYaml $c.resources | nindent 12 }}
          securityContext:
            {{- include "brandme.containerSecurityContext" $root | nindent 12 }}
          volumeMounts:
            {{- include "brandme.tmpMount" $root | nindent 12 }}
      volumes:
        {{- include "brandme.tmpVolume" $root | nindent 8 }}
{{- if .http }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $name }}
  labels:
    {{- include "brandme.labels" (list $root .component) | nindent 4 }}
spec:
  type: ClusterIP
  selector:
    {{- include "brandme.selectorLabels" (list $root .component) | nindent 4 }}
  ports:
    - name: http
      port: {{ $c.port }}
      targetPort: http
      protocol: TCP
{{- end }}
{{- end -}}
