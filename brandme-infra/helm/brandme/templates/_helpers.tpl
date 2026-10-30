{{/*
Copyright (c) Brand.Me, Inc. All rights reserved.
Shared helpers. Every value a deployment needs is checked here so rendering
fails before anything reaches a cluster.
*/}}

{{- define "brandme.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "brandme.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* Name of one component's resources: (list $ "gateway") */}}
{{- define "brandme.componentName" -}}
{{- $root := index . 0 -}}
{{- printf "%s-%s" (include "brandme.fullname" $root) (index . 1) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "brandme.selectorLabels" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ include "brandme.name" $root }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end -}}

{{- define "brandme.labels" -}}
{{- $root := index . 0 -}}
{{ include "brandme.selectorLabels" . }}
app.kubernetes.io/part-of: brandme
app.kubernetes.io/managed-by: {{ $root.Release.Service }}
app.kubernetes.io/version: {{ $root.Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" $root.Chart.Name $root.Chart.Version | replace "+" "_" }}
brandme.io/mode: {{ $root.Values.mode }}
{{- end -}}

{{/*
Required value: (list <value> "<path>"). Fails when empty or a REPLACE_ME
placeholder, otherwise returns the value.
*/}}
{{- define "brandme.req" -}}
{{- $v := index . 0 -}}
{{- $path := index . 1 -}}
{{- if or (not $v) (contains "REPLACE_ME" (toString $v)) -}}
{{- fail (printf "%s is required: set a real value in your values file (empty values and REPLACE_ME placeholders are refused)" $path) -}}
{{- end -}}
{{- $v -}}
{{- end -}}

{{- define "brandme.mode" -}}
{{- $mode := include "brandme.req" (list .Values.mode "mode") -}}
{{- if not (has $mode (list "sandbox" "production")) -}}
{{- fail (printf "mode must be sandbox or production (got %q); demo/development need local emulators and are not deployable with this chart" $mode) -}}
{{- end -}}
{{- $mode -}}
{{- end -}}

{{- define "brandme.gcpProject" -}}
{{- $p := include "brandme.req" (list .Values.gcp.projectId "gcp.projectId") -}}
{{- if not (regexMatch "^[a-z][a-z0-9-]{4,28}[a-z0-9]$" $p) -}}
{{- fail (printf "gcp.projectId %q is not a valid GCP project ID" $p) -}}
{{- end -}}
{{- $p -}}
{{- end -}}

{{/* Image reference: (list $ "core"). Digest preferred; tag allowed; latest refused. */}}
{{- define "brandme.image" -}}
{{- $root := index . 0 -}}
{{- $key := index . 1 -}}
{{- $img := index $root.Values.images $key -}}
{{- $registry := include "brandme.req" (list $root.Values.images.registry "images.registry") -}}
{{- if hasSuffix "/" $registry -}}
{{- fail "images.registry must not end with /" -}}
{{- end -}}
{{- $name := include "brandme.req" (list $img.name (printf "images.%s.name" $key)) -}}
{{- if $img.digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" $img.digest) -}}
{{- fail (printf "images.%s.digest must be sha256:<64 lowercase hex>" $key) -}}
{{- end -}}
{{- printf "%s/%s@%s" $registry $name $img.digest -}}
{{- else if $img.tag -}}
{{- if or (eq $img.tag "latest") (contains "REPLACE_ME" $img.tag) -}}
{{- fail (printf "images.%s.tag %q is refused: use an immutable tag or, preferably, a digest" $key $img.tag) -}}
{{- end -}}
{{- printf "%s/%s:%s" $registry $name $img.tag -}}
{{- else -}}
{{- fail (printf "images.%s.digest (preferred) or images.%s.tag is required" $key $key) -}}
{{- end -}}
{{- end -}}

{{/* GSA email for a component: (list $ <value> "<path>"). Accepts an account ID or a full email. */}}
{{- define "brandme.gsaEmail" -}}
{{- $root := index . 0 -}}
{{- $v := include "brandme.req" (list (index . 1) (index . 2)) -}}
{{- if contains "@" $v -}}
{{- if not (regexMatch "^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,28}[a-z0-9]\\.iam\\.gserviceaccount\\.com$" $v) -}}
{{- fail (printf "%s %q is not a user-managed GSA email" (index . 2) $v) -}}
{{- end -}}
{{- $v -}}
{{- else -}}
{{- if not (regexMatch "^[a-z][a-z0-9-]{4,28}[a-z0-9]$" $v) -}}
{{- fail (printf "%s %q is not a valid GSA account ID (6-30 chars)" (index . 2) $v) -}}
{{- end -}}
{{- printf "%s@%s.iam.gserviceaccount.com" $v (include "brandme.gcpProject" $root) -}}
{{- end -}}
{{- end -}}

{{- define "brandme.contractAddress" -}}
{{- $c := include "brandme.req" (list .Values.midnight.contractAddress "midnight.contractAddress") -}}
{{- if not (regexMatch "^[0-9a-f]{64}$" $c) -}}
{{- fail "midnight.contractAddress must be 64 lowercase hex characters" -}}
{{- end -}}
{{- $c -}}
{{- end -}}

{{- define "brandme.midnightNetwork" -}}
{{- $n := include "brandme.req" (list .Values.midnight.network "midnight.network") -}}
{{- if not (has $n (list "undeployed" "preview" "preprod")) -}}
{{- fail (printf "midnight.network %q refused: undeployed | preview | preprod (mainnet is not authorized in this build)" $n) -}}
{{- end -}}
{{- $n -}}
{{- end -}}

{{/*
consumerDomains.assertion.jwks as compact JSON (CONSUMER_DOMAIN_ASSERTION_JWKS).
Public P-256 keys only, the shape DomainAssertionVerifier.from_jwks accepts
(brandme_core/domains/persona/assertion.py:50-57). Any private or unknown
member fails the render; nothing is silently dropped.
*/}}
{{- define "brandme.consumerDomainJwks" -}}
{{- $jwks := .Values.consumerDomains.assertion.jwks -}}
{{- if not (kindIs "map" $jwks) -}}
{{- fail "consumerDomains.assertion.jwks must be a map {keys: [...]}" -}}
{{- end -}}
{{- range $member, $_ := $jwks -}}
{{- if ne $member "keys" -}}
{{- fail (printf "consumerDomains.assertion.jwks has member %q: a JWKS here holds only keys" $member) -}}
{{- end -}}
{{- end -}}
{{- $keys := $jwks.keys -}}
{{- if or (not (kindIs "slice" $keys)) (not $keys) -}}
{{- fail "consumerDomains.assertion.jwks.keys is required: the gateway's public P-256 key(s), each {kty: EC, crv: P-256, kid, x, y}" -}}
{{- end -}}
{{- $kids := list -}}
{{- range $i, $k := $keys -}}
{{- if not (kindIs "map" $k) -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d] must be a JWK map" $i) -}}
{{- end -}}
{{- if hasKey $k "d" -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d] holds a private key (\"d\"): the service takes public keys only; the private key belongs in Secret Manager (secretRefs.consumerDomainAssertionKey)" $i) -}}
{{- end -}}
{{- range $member, $_ := $k -}}
{{- if eq $member "true" -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d]: quote the y member (\"y\": ...); YAML reads a bare y key as true" $i) -}}
{{- end -}}
{{- if not (has $member (list "kty" "crv" "kid" "x" "y" "use" "alg")) -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d] has member %q: only the public members kty, crv, kid, x, y (and use, alg) are accepted" $i $member) -}}
{{- end -}}
{{- end -}}
{{- if or (ne (toString $k.kty) "EC") (ne (toString $k.crv) "P-256") -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d] must be kty EC, crv P-256 (ES256 only)" $i) -}}
{{- end -}}
{{- if or (and (hasKey $k "use") (ne (toString $k.use) "sig")) (and (hasKey $k "alg") (ne (toString $k.alg) "ES256")) -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d]: use must be sig and alg ES256 when set" $i) -}}
{{- end -}}
{{- if not (regexMatch "^[A-Za-z0-9._-]{1,64}$" (toString $k.kid)) -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d].kid must match ^[A-Za-z0-9._-]{1,64}$ (the gateway's kid format, brandme-gateway/src/config/index.ts:128)" $i) -}}
{{- end -}}
{{- if not (and (regexMatch "^[A-Za-z0-9_-]{43}$" (toString $k.x)) (regexMatch "^[A-Za-z0-9_-]{43}$" (toString $k.y))) -}}
{{- fail (printf "consumerDomains.assertion.jwks.keys[%d].x and .y must be base64url P-256 coordinates (43 characters each)" $i) -}}
{{- end -}}
{{- if has (toString $k.kid) $kids -}}
{{- fail (printf "consumerDomains.assertion.jwks has two keys with kid %q" (toString $k.kid)) -}}
{{- end -}}
{{- $kids = append $kids (toString $k.kid) -}}
{{- end -}}
{{- toJson (dict "keys" $keys) -}}
{{- end -}}

{{/* BRANDME_MODE and ENVIRONMENT always agree (read_api/config.py:26). */}}
{{- define "brandme.modeEnv" -}}
- name: BRANDME_MODE
  value: {{ include "brandme.mode" . | quote }}
- name: ENVIRONMENT
  value: {{ include "brandme.mode" . | quote }}
{{- end -}}

{{- define "brandme.spannerEnv" -}}
{{- $project := default (include "brandme.gcpProject" .) .Values.spanner.projectId -}}
- name: SPANNER_PROJECT_ID
  value: {{ $project | quote }}
- name: SPANNER_INSTANCE_ID
  value: {{ include "brandme.req" (list .Values.spanner.instanceId "spanner.instanceId") | quote }}
- name: SPANNER_DATABASE_ID
  value: {{ include "brandme.req" (list .Values.spanner.databaseId "spanner.databaseId") | quote }}
{{- end -}}

{{/* secretKeyRef env var: (list $ "ENV_NAME" "secretRefsKey") */}}
{{- define "brandme.secretEnv" -}}
{{- $root := index . 0 -}}
{{- $ref := index $root.Values.secretRefs (index . 2) -}}
- name: {{ index . 1 }}
  valueFrom:
    secretKeyRef:
      name: {{ include "brandme.req" (list $ref.name (printf "secretRefs.%s.name" (index . 2))) | quote }}
      key: {{ include "brandme.req" (list $ref.key (printf "secretRefs.%s.key" (index . 2))) | quote }}
      optional: false
{{- end -}}

{{/* Pod securityContext: (list $ <uid>) */}}
{{- define "brandme.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: {{ index . 1 }}
runAsGroup: {{ index . 1 }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "brandme.containerSecurityContext" -}}
allowPrivilegeEscalation: false
privileged: false
readOnlyRootFilesystem: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{/* Scheduling and pod-level defaults shared by every pod spec. */}}
{{- define "brandme.podDefaults" -}}
automountServiceAccountToken: {{ .Values.podDefaults.automountServiceAccountToken }}
enableServiceLinks: false
{{- with .Values.podDefaults.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.podDefaults.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.podDefaults.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/* /tmp is the only writable path; the root filesystem is read-only. */}}
{{- define "brandme.tmpVolume" -}}
- name: tmp
  emptyDir:
    sizeLimit: 64Mi
{{- end -}}

{{- define "brandme.tmpMount" -}}
- name: tmp
  mountPath: /tmp
{{- end -}}

{{/* Endpoint removal before SIGTERM (the gateway exits immediately on SIGTERM, brandme-gateway/src/index.ts:98). */}}
{{- define "brandme.preStop" -}}
lifecycle:
  preStop:
    exec:
      command: ["sleep", "5"]
{{- end -}}

{{/* NetworkPolicy egress: DNS only. */}}
{{- define "brandme.egressDns" -}}
{{- $dns := .Values.networkPolicy.dns -}}
- to:
    - namespaceSelector:
        matchLabels:
          {{- toYaml $dns.namespaceSelector | nindent 10 }}
      podSelector:
        matchLabels:
          {{- toYaml $dns.podSelector | nindent 10 }}
    {{- range $dns.cidrs }}
    - ipBlock: {cidr: {{ . }}}
    {{- end }}
  ports:
    - {port: 53, protocol: UDP}
    - {port: 53, protocol: TCP}
{{- end -}}

{{/* NetworkPolicy egress for a Google-identity workload: DNS, metadata server (Workload Identity), HTTPS. */}}
{{- define "brandme.egressBase" -}}
{{- $np := .Values.networkPolicy -}}
{{ include "brandme.egressDns" . }}
{{- range $np.metadataServer }}
- to:
    - ipBlock: {cidr: {{ .cidr }}}
  ports:
    {{- range .ports }}
    - {port: {{ . }}, protocol: TCP}
    {{- end }}
{{- end }}
- to:
    - ipBlock:
        cidr: {{ $np.httpsEgress.cidr }}
        {{- with $np.httpsEgress.except }}
        except:
          {{- toYaml . | nindent 10 }}
        {{- end }}
  ports:
    - {port: 443, protocol: TCP}
{{- end -}}

{{- define "brandme.serviceUrl" -}}
{{- $root := index . 0 -}}
{{- printf "http://%s.%s.svc.cluster.local:%v" (include "brandme.componentName" (list $root (index . 1))) $root.Release.Namespace (index . 2) -}}
{{- end -}}
