$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\work\brand-me-labs-audit'
$auditOut='C:\Users\auditor\Documents\Codex\2026-11-01\files-pasted-by-the-user-you\outputs\brand-me-labs-audit-2026-11-01-codex-01\evidence'
$auditMain='ed19dc151d103b108cf972e6d37971c55d5dcf60'
$auditRights='a05f2e03e58e55cc2b392b8abc7b19f59659f820'
$auditConsumer='babb3604ae2f33018edf0ad45270887d4b01945b'
$auditUi='0ff12fbdbce2a8b4ea1391a02ef3ea821ae6a420'
$auditText = @('# Branch static evidence excerpts', '', ('Captured '+[DateTime]::UtcNow.ToString('o')), '', 'Read only with git show; no repository code executed. Line numbers are one-based in the named immutable commit. Environment values and credentials are not included.', '')
$auditSpans=@(
 @($auditMain,'brandme-data/spanner/migrations/runner.py',91,105),
 @($auditMain,'tests/foundation/test_migrations.py',24,51),
 @($auditConsumer,'brandme-data/spanner/migrations/V016_consumer_design.sql',1,7),
 @($auditRights,'brandme-data/spanner/migrations/V016_rights_transfer_invites.sql',1,20),
 @($auditRights,'brandme_core/rights_commands/__main__.py',25,40),
 @($auditRights,'brandme-gateway/src/routes/v1/index.ts',135,165),
 @($auditRights,'brandme-gateway/src/routes/v1/transfers.ts',1,55),
 @($auditRights,'brandme_core/rights_commands/README.md',1,25),
 @($auditRights,'brandme_core/rights_commands/README.md',48,92),
 @($auditConsumer,'brandme_core/domains/persona/app.py',45,95),
 @($auditConsumer,'brandme_core/domains/rewards/credits.py',174,202),
 @($auditUi,'brandme-frontend/features/social/horizons.tsx',1,40),
 @($auditMain,'docs/build/orchestration/pipeline-state.md',8,22),
 @($auditMain,'docs/build/orchestration/pipeline-state.md',61,103),
 @($auditMain,'.github/workflows/consumer-ui.yml',1,8),
 @($auditMain,'.github/workflows/spatial-validation.yml',1,8),
 @($auditMain,'pnpm-workspace.yaml',1,13),
 @($auditMain,'.github/workflows/module-regression.yml',30,49),
 @($auditMain,'tests/contracts/property.test.ts',218,270)
)
foreach($auditSpan in $auditSpans){
 $auditSha,$auditPath,$auditStart,$auditEnd=$auditSpan
 $auditLines=@(git show "${auditSha}:$auditPath")
 $auditText += ('## '+$auditPath+' @ '+$auditSha), '', ('https://github.com/brandmeonline/Brand-Me-Labs/blob/'+$auditSha+'/'+$auditPath+'#L'+$auditStart), '', '```text'
 for($auditLine=$auditStart; $auditLine -le [Math]::Min($auditEnd,$auditLines.Count); $auditLine++){ $auditText+=('{0}: {1}' -f $auditLine,$auditLines[$auditLine-1]) }
 $auditText += '```',''
}
$auditUiStatus=@(git show "${auditUi}:docs/build/status/astra-consumer-ui.md")
$auditText += '## Preview handoff correction @ '+$auditUi,'','```text'
for($auditLine=[Math]::Max(1,$auditUiStatus.Count-85);$auditLine -le $auditUiStatus.Count;$auditLine++){ $auditText+=('{0}: {1}' -f $auditLine,$auditUiStatus[$auditLine-1]) }
$auditText += '```','','## Consumer credit call-site search','','Command: git grep -n apply_credit babb3604ae2f33018edf0ad45270887d4b01945b -- :!docs :!pnpm-lock.yaml','','```text'
$auditText += @(git grep -n 'apply_credit' $auditConsumer -- ':!docs' ':!pnpm-lock.yaml')
$auditText += '```','','## Rights router mount and trust-path search','','git grep -n createTransfersRouter a05f2e03e58e55cc2b392b8abc7b19f59659f820 -- brandme-gateway/src/routes/v1/index.ts: no matches, exit 1.','','git grep -n rights_commands a05f2e03e58e55cc2b392b8abc7b19f59659f820 -- brandme_core/config.py: no matches, exit 1.',''
git grep -n createTransfersRouter $auditRights -- brandme-gateway/src/routes/v1/index.ts | Out-Null
if($LASTEXITCODE -ne 1){ throw 'Unexpected transfer mount search result' }
git grep -n rights_commands $auditRights -- brandme_core/config.py | Out-Null
if($LASTEXITCODE -ne 1){ throw 'Unexpected trust-path search result' }
$auditText | Set-Content -LiteralPath (Join-Path $auditOut 'history-source-excerpts.md') -Encoding utf8
Write-Output ('Saved '+$auditText.Count+' source evidence lines')
